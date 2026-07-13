# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from ...domain.entities import MissionAssignment
from ...domain.enums import Status
from ...domain.exceptions import NotFoundError
from ...infrastructure.base import RepositoryAdapter
from .models import ActivityRow, AssignmentRow, ObjectiveRow
from ._cascade import delete_objective_subtree
from ._mappers import (
    activity_from_row,
    assignment_from_row,
    assignment_to_row,
    objective_from_row,
)


class SqlAlchemyMissionAssignmentRepository(RepositoryAdapter[MissionAssignment]):

    def __init__(self, session: Session) -> None:
        self._s = session

    def _load_assignment(self, row: AssignmentRow) -> MissionAssignment:
        obj_rows = (
            self._s.query(ObjectiveRow)
            .filter(ObjectiveRow.assignment_id == row.id)
            .all()
        )
        objectives = []
        for obj_row in obj_rows:
            act_rows = (
                self._s.query(ActivityRow)
                .filter(ActivityRow.objective_id == obj_row.id)
                .all()
            )
            activities = [activity_from_row(r) for r in act_rows]
            objectives.append(objective_from_row(obj_row, activities))
        return assignment_from_row(row, objectives)

    def get(self, id: UUID) -> MissionAssignment:
        row = self._s.get(AssignmentRow, id)
        if row is None:
            raise NotFoundError(f"Assignment {id} non trovato", resource_type="assignment", resource_id=id)
        return self._load_assignment(row)

    def list(self, filters: dict) -> list[MissionAssignment]:
        rows = self._s.query(AssignmentRow).all()
        return [self._load_assignment(r) for r in rows]

    def save(self, entity: MissionAssignment) -> MissionAssignment:
        existing = self._s.get(AssignmentRow, entity.id)
        row = assignment_to_row(entity, existing)
        if existing is None:
            self._s.add(row)

        # Replace objectives + activities belonging to this assignment
        delete_objective_subtree(self._s, ObjectiveRow.assignment_id == entity.id)

        # Inserisci prima tutti gli obiettivi, poi le attività. Tra ObjectiveRow
        # e ActivityRow non esiste una relationship(): la unit-of-work di
        # SQLAlchemy non deduce dalla sola FK activity.objective_id che
        # l'obiettivo vada inserito per primo e può emettere l'INSERT delle
        # attività prima di quello dell'obiettivo. Su backend che applicano i
        # vincoli (MySQL/PostgreSQL) questo fa fallire l'INSERT con un errore di
        # foreign key; il flush intermedio garantisce l'ordine corretto.
        for obj in entity.objectives:
            obj_row = ObjectiveRow(
                id=obj.id,
                description=obj.description,
                mission_id=None,
                assignment_id=entity.id,
            )
            self._s.add(obj_row)
        self._s.flush()

        for obj in entity.objectives:
            for act in obj.activities:
                act_row = ActivityRow(
                    id=act.id,
                    title=act.title,
                    description=act.description,
                    status=act.status.value,
                    objective_id=obj.id,
                    assignees=[str(a) for a in act.assignees],
                    badge_award_id=act.badge_award.id if act.badge_award else None,
                )
                self._s.add(act_row)

        self._s.flush()
        return entity

    def delete(self, id: UUID) -> bool:
        row = self._s.get(AssignmentRow, id)
        if row is None:
            return False
        delete_objective_subtree(self._s, ObjectiveRow.assignment_id == id)
        self._s.delete(row)
        self._s.flush()
        return True

    def exists(self, id: UUID) -> bool:
        return self._s.get(AssignmentRow, id) is not None

    def get_by_mission(self, mission_id: UUID) -> list[MissionAssignment]:
        rows = self._s.query(AssignmentRow).filter(AssignmentRow.mission_id == mission_id).all()
        return [self._load_assignment(r) for r in rows]

    def get_by_assignee(self, assignee_id: UUID) -> list[MissionAssignment]:
        rows = self._s.query(AssignmentRow).filter(AssignmentRow.assignee_id == assignee_id).all()
        return [self._load_assignment(r) for r in rows]

    def get_by_status(self, status: Status) -> list[MissionAssignment]:
        rows = self._s.query(AssignmentRow).filter(AssignmentRow.status == status.value).all()
        return [self._load_assignment(r) for r in rows]

    def count_by_mission(self, mission_id: UUID) -> int:
        return self._s.query(AssignmentRow).filter(AssignmentRow.mission_id == mission_id).count()

    def count_active_by_mission(self, mission_id: UUID) -> int:
        active_statuses = [Status.ASSIGNED.value, Status.IN_PROGRESS.value]
        return (
            self._s.query(AssignmentRow)
            .filter(
                AssignmentRow.mission_id == mission_id,
                AssignmentRow.status.in_(active_statuses),
            )
            .count()
        )
