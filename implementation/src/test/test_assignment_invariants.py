# SPDX-License-Identifier: CC-BY-SA-4.0
"""Regressioni per invarianti, transazioni ed eventi degli assignment."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from src.application.services._shared import acl_bypass
from src.domain.entities import Activity, Mission, Objective
from src.domain.enums import AssigneeType, Status
from src.domain.exceptions import ValidationError
from src.domain.value_objects import AssignmentPolicy
from src.frontend.api.middleware import _rate_limited_operation
from src.infrastructure.security.rate_limit import RateLimitedOperation


def _read(callable_, *args, **kwargs):
    with acl_bypass():
        return callable_(*args, **kwargs)


def _mission_payload() -> dict:
    return {
        "title": "Operazione",
        "desc": "",
        "objectives": [
            {"description": "Obiettivo", "activities": [{"title": "Attività"}]}
        ],
    }


def _create_assigned(svcs, operator_id: UUID):
    mission = svcs.mission.create(**_mission_payload(), operator_id=operator_id)
    assignment = svcs.assignment.create(
        mission.id,
        AssigneeType.PERSON.value,
        str(operator_id),
        operator_id=operator_id,
    )
    return mission, assignment


def test_assignment_cannot_complete_before_all_activities_complete(web_app, seed_admin):
    _, svcs = web_app
    operator = seed_admin(svcs)
    _, assignment = _create_assigned(svcs, UUID(operator.id))

    svcs.assignment.update_status(
        assignment.id, Status.IN_PROGRESS.value, operator_id=UUID(operator.id)
    )
    with pytest.raises(ValidationError, match="tutte le attività"):
        svcs.assignment.update_status(
            assignment.id, Status.COMPLETED.value, operator_id=UUID(operator.id)
        )


def test_activity_in_progress_automatically_starts_parent_assignment(web_app, seed_admin):
    """ASSIGNED → IN_PROGRESS si propaga automaticamente all'assignment padre
    appena almeno una sua attività passa a IN_PROGRESS."""
    _, svcs = web_app
    operator = seed_admin(svcs)
    op = UUID(operator.id)
    _, assignment = _create_assigned(svcs, op)
    activity = assignment.objectives[0].activities[0]
    assert _read(svcs.assignment.get, assignment.id).status == Status.ASSIGNED.value

    svcs.activity.assign_to(activity.id, operator.id, operator_id=op)
    # ancora ASSIGNED: assegnare un'attività non avvia l'assignment
    assert _read(svcs.assignment.get, assignment.id).status == Status.ASSIGNED.value

    result = svcs.activity.update_status(
        activity.id, Status.IN_PROGRESS.value, operator_id=op
    )
    assert result.status == Status.IN_PROGRESS.value
    # cascade automatico: l'assignment padre è ora IN_PROGRESS
    assert _read(svcs.assignment.get, assignment.id).status == Status.IN_PROGRESS.value


def test_failed_activity_automatically_fails_parent_assignment(web_app, seed_admin):
    _, svcs = web_app
    operator = seed_admin(svcs)
    _, assignment = _create_assigned(svcs, UUID(operator.id))
    activity = assignment.objectives[0].activities[0]

    svcs.activity.assign_to(activity.id, operator.id, operator_id=UUID(operator.id))
    result = svcs.activity.update_status(
        activity.id, Status.FAILED.value, operator_id=UUID(operator.id)
    )

    assert result.status == Status.FAILED.value
    assert _read(svcs.assignment.get, assignment.id).status == Status.FAILED.value


def test_unassign_is_only_allowed_before_start_and_restores_unassigned(web_app, seed_admin):
    _, svcs = web_app
    operator = seed_admin(svcs)
    _, assignment = _create_assigned(svcs, UUID(operator.id))
    activity = assignment.objectives[0].activities[0]

    svcs.activity.assign_to(activity.id, operator.id, operator_id=UUID(operator.id))
    result = svcs.activity.unassign(
        activity.id, operator.id, operator_id=UUID(operator.id)
    )
    assert result.status == Status.UNASSIGNED.value
    assert result.assignees == []

    svcs.activity.assign_to(activity.id, operator.id, operator_id=UUID(operator.id))
    svcs.activity.update_status(
        activity.id, Status.IN_PROGRESS.value, operator_id=UUID(operator.id)
    )
    with pytest.raises(ValidationError, match="dopo l'inizio"):
        svcs.activity.unassign(activity.id, operator.id, operator_id=UUID(operator.id))


def test_assignee_pair_is_atomic_and_concurrency_is_checked_on_assign(web_app, seed_admin):
    _, svcs = web_app
    operator = seed_admin(svcs)
    operator_id = UUID(operator.id)

    mission_id = uuid4()
    objective_id = uuid4()
    mission = Mission(
        id=mission_id,
        title="Limite",
        description="",
        assignment_policy=AssignmentPolicy.once_active(),
        objectives=[
            Objective(
                id=objective_id,
                mission_id=mission_id,
                description="O",
                activities=[
                    Activity(
                        id=uuid4(),
                        title="A",
                        description="",
                        status=Status.UNASSIGNED,
                        objective_id=objective_id,
                    )
                ],
            )
        ],
    )
    with svcs.uow.transaction():
        svcs.mission._mission_repo.save(mission)

    with pytest.raises(ValidationError, match="forniti insieme"):
        svcs.assignment.create(
            str(mission_id), AssigneeType.PERSON.value, None, operator_id=operator_id
        )

    first = svcs.assignment.create(str(mission_id), operator_id=operator_id)
    second = svcs.assignment.create(str(mission_id), operator_id=operator_id)
    svcs.assignment.assign(
        first.id, AssigneeType.PERSON.value, operator.id, operator_id=operator_id
    )
    with pytest.raises(ValidationError, match="assegnazioni attive"):
        svcs.assignment.assign(
            second.id, AssigneeType.PERSON.value, operator.id, operator_id=operator_id
        )

    # Una bozza resta consentita anche dopo aver raggiunto il limite: non è
    # un assignment operativo finché non riceve un assegnatario.
    third = svcs.assignment.create(str(mission_id), operator_id=operator_id)
    assert third.status == Status.UNASSIGNED.value

    with pytest.raises(ValidationError, match="ultimo assegnatario"):
        svcs.assignment.update_status(
            first.id, Status.UNASSIGNED.value, operator_id=operator_id
        )


def test_cascade_rolls_back_if_parent_write_fails(web_app, seed_admin, monkeypatch):
    _, svcs = web_app
    operator = seed_admin(svcs)
    _, assignment = _create_assigned(svcs, UUID(operator.id))
    activity = assignment.objectives[0].activities[0]
    svcs.activity.assign_to(activity.id, operator.id, operator_id=UUID(operator.id))

    original_save = svcs.assignment._assignment_repo.save

    def fail_parent_save(entity):
        if entity.id == UUID(assignment.id) and entity.status == Status.IN_PROGRESS:
            raise RuntimeError("simulated database failure")
        return original_save(entity)

    monkeypatch.setattr(svcs.assignment._assignment_repo, "save", fail_parent_save)
    with pytest.raises(RuntimeError, match="simulated"):
        svcs.activity.update_status(
            activity.id, Status.IN_PROGRESS.value, operator_id=UUID(operator.id)
        )

    assert _read(svcs.activity.get, activity.id).status == Status.ASSIGNED.value


def test_events_are_persisted_with_the_real_operator_and_audited(web_app, seed_admin):
    _, svcs = web_app
    operator = seed_admin(svcs)
    mission = svcs.mission.create(**_mission_payload(), operator_id=UUID(operator.id))

    with svcs.uow.transaction():
        rows = svcs.session.execute(text("select event_type, payload from mm_outbox_events")).all()
    assert rows[-1][0] == "MissionCreated"
    assert json.loads(rows[-1][1])["operator_id"] == operator.id

    assert svcs.event_publisher.dispatch_consumer("audit") == 1
    with svcs.uow.transaction():
        deliveries = svcs.session.execute(
            text("select count(*) from mm_outbox_deliveries where consumer = 'audit'")
        ).scalar_one()
    assert deliveries == 1


def test_every_supported_rest_mutation_is_rate_limited():
    assert _rate_limited_operation("/api/assignments/a/assign", "POST") == (
        RateLimitedOperation.ASSIGN_ASSIGNMENT
    )
    assert _rate_limited_operation("/api/activities/a/assign", "DELETE") == (
        RateLimitedOperation.UNASSIGN_ACTIVITY
    )
    assert _rate_limited_operation("/api/groups", "POST") == (
        RateLimitedOperation.CREATE_GROUP
    )
    assert _rate_limited_operation("/api/extensions/report/run", "POST") == (
        RateLimitedOperation.OTHER_MUTATION
    )
