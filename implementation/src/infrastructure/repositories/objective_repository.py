# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from ...domain.entities import Objective
from ...domain.exceptions import NotFoundError
from ...infrastructure.base import RepositoryAdapter
from .models import ActivityRow, ObjectiveRow
from ._mappers import activity_from_row, objective_from_row, objective_to_row


class SqlAlchemyObjectiveRepository(RepositoryAdapter[Objective]):

    def __init__(self, session: Session) -> None:
        self._s = session

    def _load(self, row: ObjectiveRow) -> Objective:
        act_rows = (
            self._s.query(ActivityRow)
            .filter(ActivityRow.objective_id == row.id)
            .all()
        )
        activities = [activity_from_row(r) for r in act_rows]
        return objective_from_row(row, activities)

    def get(self, id: UUID) -> Objective:
        row = self._s.get(ObjectiveRow, id)
        if row is None:
            raise NotFoundError(f"Objective {id} non trovato", resource_type="objective", resource_id=id)
        return self._load(row)

    def list(self, filters: dict) -> list[Objective]:
        rows = self._s.query(ObjectiveRow).all()
        return [self._load(r) for r in rows]

    def save(self, entity: Objective) -> Objective:
        existing = self._s.get(ObjectiveRow, entity.id)
        row = objective_to_row(entity, existing)
        if existing is None:
            self._s.add(row)
        self._s.flush()
        return entity

    def delete(self, id: UUID) -> bool:
        row = self._s.get(ObjectiveRow, id)
        if row is None:
            return False
        self._s.query(ActivityRow).filter(ActivityRow.objective_id == id).delete()
        self._s.delete(row)
        self._s.flush()
        return True

    def exists(self, id: UUID) -> bool:
        return self._s.get(ObjectiveRow, id) is not None

    def get_by_assignment(self, assignment_id: UUID) -> list[Objective]:
        rows = (
            self._s.query(ObjectiveRow)
            .filter(ObjectiveRow.assignment_id == assignment_id)
            .all()
        )
        return [self._load(r) for r in rows]
