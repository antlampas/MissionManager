# SPDX-License-Identifier: CC-BY-SA-4.0
"""Invarianti di dominio del MissionService."""
import uuid

import pytest

from src.application.services._shared import acl_bypass
from src.domain.entities import Activity, Objective
from src.domain.enums import Status
from src.domain.exceptions import ValidationError

OP = uuid.uuid4()


def _blueprint():
    return {"title": "Op", "desc": "", "objectives": [
        {"description": "O", "activities": [{"title": "A"}]}
    ], "operator_id": OP}


def test_create_requires_at_least_one_objective(web_app):
    _, svcs = web_app
    with pytest.raises(ValidationError):
        with acl_bypass():
            svcs.mission.create(title="Op", desc="", objectives=[], operator_id=OP)


def test_create_requires_objective_with_activity(web_app):
    _, svcs = web_app
    with pytest.raises(ValidationError):
        with acl_bypass():
            svcs.mission.create(
                title="Op", desc="",
                objectives=[{"description": "O", "activities": []}], operator_id=OP
            )


def test_create_requires_activity_title(web_app):
    _, svcs = web_app
    with pytest.raises(ValidationError, match="titolo"):
        with acl_bypass():
            svcs.mission.create(
                title="Op",
                desc="",
                objectives=[{"description": "O", "activities": [{"title": "   "}]}],
                operator_id=OP,
            )


def test_objective_rejects_activity_from_another_objective():
    objective_id = uuid.uuid4()
    other_id = uuid.uuid4()
    objective = Objective(
        id=objective_id,
        description="O",
        activities=[
            Activity(
                id=uuid.uuid4(),
                title="A",
                description="",
                status=Status.UNASSIGNED,
                objective_id=other_id,
            )
        ],
    )
    with pytest.raises(ValidationError, match="obiettivo corrente"):
        objective.validate()


def test_blueprint_is_immutable_after_creation(web_app):
    """Il blueprint è immutabile: nessuna API per aggiungere/modificare
    obiettivi o attività dopo la creazione (né su Mission né su MissionService)."""
    from src.domain.entities import Mission

    _, svcs = web_app
    assert not hasattr(svcs.mission, "add_objective")
    assert not hasattr(Mission, "add_objective")
