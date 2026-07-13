# SPDX-License-Identifier: CC-BY-SA-4.0
"""Persistenza del sotto-albero missione → obiettivi → attività.

Protegge l'ordine FK-safe degli INSERT (obiettivi prima delle attività) e il
cascade-delete condiviso da mission e assignment repository.
"""
import uuid

from sqlalchemy import text

from src.domain.entities import Activity, Mission, MissionAssignment, Objective
from src.domain.enums import Status
from src.domain.value_objects import AssignmentPolicy
from src.infrastructure.repositories.assignment_repository import (
    SqlAlchemyMissionAssignmentRepository,
)
from src.infrastructure.repositories.mission_repository import SqlAlchemyMissionRepository


def _objectives(parent_id, n_obj=1, n_act=3):
    objs = []
    for _ in range(n_obj):
        oid = uuid.uuid4()
        acts = [
            Activity(
                id=uuid.uuid4(),
                title=f"A{i}",
                description="",
                status=Status.UNASSIGNED,
                objective_id=oid,
                assignees=[],
            )
            for i in range(n_act)
        ]
        objs.append(Objective(id=oid, description="O", activities=acts, mission_id=parent_id))
    return objs


def _mission(n_obj=1, n_act=3):
    mid = uuid.uuid4()
    return Mission(
        id=mid,
        title="Op",
        description="",
        assignment_policy=AssignmentPolicy.unlimited(),
        objectives=_objectives(mid, n_obj, n_act),
    )


def _count(session, table):
    return session.execute(text(f"select count(*) from {table}")).scalar()


def test_mission_save_inserts_objectives_before_activities(fk_session):
    mission = _mission(n_obj=1, n_act=3)
    SqlAlchemyMissionRepository(fk_session).save(mission)
    assert _count(fk_session, "mm_objectives") == 1
    assert _count(fk_session, "mm_activities") == 3


def test_mission_resave_replaces_blueprint(fk_session):
    repo = SqlAlchemyMissionRepository(fk_session)
    mission = _mission(n_obj=1, n_act=3)
    repo.save(mission)
    mission.objectives = _objectives(mission.id, n_obj=2, n_act=2)
    repo.save(mission)
    assert _count(fk_session, "mm_objectives") == 2
    assert _count(fk_session, "mm_activities") == 4


def test_mission_delete_cascades(fk_session):
    repo = SqlAlchemyMissionRepository(fk_session)
    mission = _mission(n_obj=1, n_act=3)
    repo.save(mission)
    assert repo.delete(str(mission.id)) is True
    assert _count(fk_session, "mm_missions") == 0
    assert _count(fk_session, "mm_objectives") == 0
    assert _count(fk_session, "mm_activities") == 0


def test_assignment_save_and_delete_cascade(fk_session):
    mission = _mission(n_obj=1, n_act=1)  # serve per la FK assignment.mission_id
    SqlAlchemyMissionRepository(fk_session).save(mission)

    arepo = SqlAlchemyMissionAssignmentRepository(fk_session)
    aid = uuid.uuid4()
    assignment = MissionAssignment(
        id=aid, mission_id=mission.id, status=Status.UNASSIGNED, objectives=_objectives(aid, 1, 2)
    )
    arepo.save(assignment)
    assert _count(fk_session, "mm_objectives") == 2  # 1 blueprint + 1 assignment
    assert _count(fk_session, "mm_activities") == 3  # 1 blueprint + 2 assignment

    assert arepo.delete(str(aid)) is True
    # rimossi solo gli obiettivi/attività dell'assignment, non il blueprint
    assert _count(fk_session, "mm_objectives") == 1
    assert _count(fk_session, "mm_activities") == 1
