# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from ...domain.entities import Group
from ...domain.exceptions import NotFoundError
from ...infrastructure.group_repository import GroupRepositoryAdapter
from .models import GroupRow, ZoneRow, _person_group
from ._mappers import group_from_row, group_to_row, zone_to_row


class SqlAlchemyGroupRepository(GroupRepositoryAdapter):

    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, id: UUID) -> Group:
        row = self._s.get(GroupRow, id)
        if row is None:
            raise NotFoundError(f"Group {id} non trovato", resource_type="group", resource_id=id)
        return group_from_row(row)

    def list(self, filters: dict) -> list[Group]:
        rows = self._s.query(GroupRow).all()
        return [group_from_row(r) for r in rows]

    def save(self, entity: Group) -> Group:
        # Persist Zone if present
        if entity.zone:
            existing_zone = self._s.get(ZoneRow, entity.zone.id)
            zone_row = zone_to_row(entity.zone, existing_zone)
            if existing_zone is None:
                self._s.add(zone_row)

        existing = self._s.get(GroupRow, entity.id)
        row = group_to_row(entity, existing)
        if existing is None:
            self._s.add(row)
        self._s.flush()
        return entity

    def delete(self, id: UUID) -> bool:
        row = self._s.get(GroupRow, id)
        if row is None:
            return False
        self._s.execute(
            _person_group.delete().where(_person_group.c.group_id == id)
        )
        self._s.delete(row)
        self._s.flush()
        return True

    def exists(self, id: UUID) -> bool:
        return self._s.get(GroupRow, id) is not None

    def add_member(self, group_id: UUID, person_id: UUID) -> None:
        already = self._s.execute(
            _person_group.select().where(
                _person_group.c.group_id == group_id,
                _person_group.c.person_id == person_id,
            )
        ).first()
        if already is not None:
            raise ValueError("La persona è già membro del gruppo")
        self._s.execute(
            _person_group.insert().values(group_id=group_id, person_id=person_id)
        )
        self._s.flush()

    def remove_member(self, group_id: UUID, person_id: UUID) -> None:
        self._s.execute(
            _person_group.delete().where(
                _person_group.c.group_id == group_id,
                _person_group.c.person_id == person_id,
            )
        )
        self._s.flush()
