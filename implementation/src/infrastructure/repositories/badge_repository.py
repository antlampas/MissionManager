# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from ...domain.entities import Badge
from ...domain.exceptions import NotFoundError
from ...infrastructure.base import RepositoryAdapter
from .models import BadgeRow
from ._mappers import badge_from_row, badge_to_row


class SqlAlchemyBadgeRepository(RepositoryAdapter[Badge]):

    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, id: UUID) -> Badge:
        row = self._s.get(BadgeRow, id)
        if row is None:
            raise NotFoundError(f"Badge {id} non trovato", resource_type="badge", resource_id=id)
        return badge_from_row(row)

    def list(self, filters: dict) -> list[Badge]:
        rows = self._s.query(BadgeRow).all()
        return [badge_from_row(r) for r in rows]

    def save(self, entity: Badge) -> Badge:
        existing = self._s.get(BadgeRow, entity.id)
        row = badge_to_row(entity, existing)
        if existing is None:
            self._s.add(row)
        self._s.flush()
        return entity

    def delete(self, id: UUID) -> bool:
        row = self._s.get(BadgeRow, id)
        if row is None:
            return False
        self._s.delete(row)
        self._s.flush()
        return True

    def exists(self, id: UUID) -> bool:
        return self._s.get(BadgeRow, id) is not None
