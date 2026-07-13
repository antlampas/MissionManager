# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ...domain.entities import BadgeAward
from ...domain.exceptions import NotFoundError
from ...infrastructure.base import RepositoryAdapter
from .models import BadgeAwardRow
from ._mappers import badge_award_from_row, badge_award_to_row


class SqlAlchemyBadgeAwardRepository(RepositoryAdapter[BadgeAward]):

    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, id: UUID) -> BadgeAward:
        row = self._s.get(BadgeAwardRow, id)
        if row is None:
            raise NotFoundError(f"BadgeAward {id} non trovato", resource_type="badge_award", resource_id=id)
        return badge_award_from_row(row)

    def list(self, filters: dict) -> list[BadgeAward]:
        rows = self._s.query(BadgeAwardRow).all()
        return [badge_award_from_row(r) for r in rows]

    def save(self, entity: BadgeAward) -> BadgeAward:
        existing = self._s.get(BadgeAwardRow, entity.id)
        row = badge_award_to_row(entity, existing)
        if existing is None:
            self._s.add(row)
        self._s.flush()
        return entity

    def delete(self, id: UUID) -> bool:
        row = self._s.get(BadgeAwardRow, id)
        if row is None:
            return False
        self._s.delete(row)
        self._s.flush()
        return True

    def exists(self, id: UUID) -> bool:
        return self._s.get(BadgeAwardRow, id) is not None

    def get_by_person(self, person_id: UUID) -> list[BadgeAward]:
        person_str = str(person_id)
        rows = self._s.query(BadgeAwardRow).all()
        return [
            badge_award_from_row(r)
            for r in rows
            if person_str in (r.recipients or [])
        ]

    def get_by_assignment(self, assignment_id: UUID) -> Optional[BadgeAward]:
        row = (
            self._s.query(BadgeAwardRow)
            .filter(
                BadgeAwardRow.target_type == "ASSIGNMENT",
                BadgeAwardRow.target_id == assignment_id,
            )
            .first()
        )
        return badge_award_from_row(row) if row else None

    def get_by_activity(self, activity_id: UUID) -> Optional[BadgeAward]:
        row = (
            self._s.query(BadgeAwardRow)
            .filter(
                BadgeAwardRow.target_type == "ACTIVITY",
                BadgeAwardRow.target_id == activity_id,
            )
            .first()
        )
        return badge_award_from_row(row) if row else None

    def exists_for_target(self, target_type: str, target_id: UUID) -> bool:
        return (
            self._s.query(BadgeAwardRow)
            .filter(
                BadgeAwardRow.target_type == target_type,
                BadgeAwardRow.target_id == target_id,
            )
            .count()
            > 0
        )
