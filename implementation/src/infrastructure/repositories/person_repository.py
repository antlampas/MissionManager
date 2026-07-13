# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ...domain.entities import Person
from ...domain.exceptions import NotFoundError
from ...infrastructure.person_repository import PersonRepositoryAdapter
from .models import GroupRow, PersonRow, _person_group
from ._mappers import person_from_row, person_to_row


class SqlAlchemyPersonRepository(PersonRepositoryAdapter):

    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, id: UUID) -> Person:
        row = self._s.get(PersonRow, id)
        if row is None:
            raise NotFoundError(f"Person {id} non trovata", resource_type="person", resource_id=id)
        return person_from_row(row)

    def list(self, filters: dict) -> list[Person]:
        rows = self._s.query(PersonRow).all()
        return [person_from_row(r) for r in rows]

    def save(self, entity: Person) -> Person:
        existing = self._s.get(PersonRow, entity.id)
        row = person_to_row(entity, existing)
        if existing is None:
            self._s.add(row)
        self._s.flush()
        return entity

    def delete(self, id: UUID) -> bool:
        row = self._s.get(PersonRow, id)
        if row is None:
            return False
        self._s.execute(
            _person_group.delete().where(_person_group.c.person_id == id)
        )
        self._s.delete(row)
        self._s.flush()
        return True

    def exists(self, id: UUID) -> bool:
        return self._s.get(PersonRow, id) is not None

    def get_by_group(self, group_id: UUID) -> list[Person]:
        group_row = self._s.get(GroupRow, group_id)
        if group_row is None:
            return []
        return [person_from_row(p) for p in group_row.members]

    def get_by_nickname(self, nickname: str) -> Optional[Person]:
        for row in self._s.query(PersonRow).all():
            if nickname in (row.nicknames or []):
                return person_from_row(row)
        return None
