# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from ...domain.entities import Activity
from ...domain.exceptions import NotFoundError
from ...infrastructure.base import RepositoryAdapter
from .models import ActivityRow
from ._mappers import activity_from_row, activity_to_row


class SqlAlchemyActivityRepository(RepositoryAdapter[Activity]):

    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, id: UUID) -> Activity:
        row = self._s.get(ActivityRow, id)
        if row is None:
            raise NotFoundError(f"Activity {id} non trovata", resource_type="activity", resource_id=id)
        return activity_from_row(row)

    def list(self, filters: dict) -> list[Activity]:
        rows = self._s.query(ActivityRow).all()
        return [activity_from_row(r) for r in rows]

    def save(self, entity: Activity) -> Activity:
        existing = self._s.get(ActivityRow, entity.id)
        row = activity_to_row(entity, existing)
        if existing is None:
            self._s.add(row)
        self._s.flush()
        return entity

    def delete(self, id: UUID) -> bool:
        row = self._s.get(ActivityRow, id)
        if row is None:
            return False
        self._s.delete(row)
        self._s.flush()
        return True

    def exists(self, id: UUID) -> bool:
        return self._s.get(ActivityRow, id) is not None

    def get_by_objective(self, objective_id: UUID) -> list[Activity]:
        rows = (
            self._s.query(ActivityRow)
            .filter(ActivityRow.objective_id == objective_id)
            .all()
        )
        return [activity_from_row(r) for r in rows]

    def get_by_person(self, person_id: UUID) -> list[Activity]:
        # Filters via JSON: load all and filter in Python
        # (JSON array contains check is dialect-specific)
        rows = self._s.query(ActivityRow).all()
        person_str = str(person_id)
        return [
            activity_from_row(r)
            for r in rows
            if person_str in (r.assignees or [])
        ]
