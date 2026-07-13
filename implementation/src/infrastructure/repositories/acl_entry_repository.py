# SPDX-License-Identifier: CC-BY-SA-4.0
"""SQLAlchemy adapter for the reusable ``acl`` entry repository port."""
from __future__ import annotations

from uuid import UUID

from ...domain.acl import (
    AclEntry,
    JoinOp,
    Operation,
    Permission,
    ResourceRef,
    SubjectRef,
    SubjectType,
    from_external_resource,
)
from ...domain.enums import ResourceType
from .models import AclEntryRow


class SqlAlchemyAclEntryRepository:
    def __init__(self, session) -> None:
        self._s = session

    def get(self, entry_id: UUID) -> AclEntry | None:
        row = self._s.get(AclEntryRow, self._entry_id(entry_id))
        return self._from_row(row) if row is not None else None

    def list_for(self, resource: ResourceRef, operation: Operation) -> list[AclEntry]:
        return self.entries_for(resource, operation)

    def entries_for(self, resource: ResourceRef, operation: Operation | str) -> list[AclEntry]:
        resource = from_external_resource(resource)
        rows = (
            self._s.query(AclEntryRow)
            .filter(
                AclEntryRow.resource_type == resource.type_value,
                AclEntryRow.resource_id == resource.key(),
                AclEntryRow.operation == self._operation_value(operation),
            )
            .all()
        )
        return [self._from_row(row) for row in rows]

    def list_by_resource(self, resource: ResourceRef) -> list[AclEntry]:
        resource = from_external_resource(resource)
        rows = (
            self._s.query(AclEntryRow)
            .filter(
                AclEntryRow.resource_type == resource.type_value,
                AclEntryRow.resource_id == resource.key(),
            )
            .all()
        )
        return [self._from_row(row) for row in rows]

    def list_by_operation(self, operation: Operation | str, resource_type: str) -> list[AclEntry]:
        rows = (
            self._s.query(AclEntryRow)
            .filter(
                AclEntryRow.resource_type == str(resource_type).strip().upper(),
                AclEntryRow.operation == self._operation_value(operation),
            )
            .all()
        )
        return [self._from_row(row) for row in rows]

    def list_all(self) -> list[AclEntry]:
        rows = (
            self._s.query(AclEntryRow)
            .order_by(
                AclEntryRow.resource_type,
                AclEntryRow.resource_id,
                AclEntryRow.operation,
            )
            .all()
        )
        return [self._from_row(row) for row in rows]

    def save(self, entry: AclEntry) -> AclEntry:
        row = self._s.get(AclEntryRow, self._entry_id(entry.id))
        if row is None:
            row = AclEntryRow(id=self._entry_id(entry.id))
            self._s.add(row)
        row.subject_type = entry.subject.type.value
        row.subject_id = entry.subject.id
        resource = from_external_resource(entry.resource)
        row.resource_type = resource.type_value
        row.resource_id = resource.key()
        row.operation = self._operation_value(entry.operation)
        row.permission = entry.permission.value
        row.level = entry.level
        row.group = entry.group
        row.profile_join = entry.profile_join.value
        row.subject_join = entry.subject_join.value
        self._s.flush()
        return entry

    def delete(self, entry_id: UUID) -> bool:
        row = self._s.get(AclEntryRow, self._entry_id(entry_id))
        if row is None:
            return False
        self._s.delete(row)
        self._s.flush()
        return True

    def delete_by_resource(self, resource: ResourceRef) -> None:
        resource = from_external_resource(resource)
        self._s.query(AclEntryRow).filter(
            AclEntryRow.resource_type == resource.type_value,
            AclEntryRow.resource_id == resource.key(),
        ).delete(synchronize_session="fetch")
        self._s.flush()

    def delete_by_subject(self, subject: SubjectRef) -> None:
        self._s.query(AclEntryRow).filter(
            AclEntryRow.subject_type == subject.type.value,
            AclEntryRow.subject_id == subject.id,
        ).delete(synchronize_session="fetch")
        self._s.flush()

    def replace_entries(self, resource: ResourceRef, entries) -> None:
        self.delete_by_resource(resource)
        for entry in entries:
            self.save(entry)

    def is_empty(self) -> bool:
        return self._s.query(AclEntryRow).first() is None

    @staticmethod
    def _from_row(row: AclEntryRow) -> AclEntry:
        return AclEntry(
            id=row.id,
            subject=SubjectRef(SubjectType(row.subject_type), row.subject_id),
            resource=ResourceRef(ResourceType(row.resource_type), row.resource_id),
            operation=Operation(row.operation),
            permission=Permission(row.permission),
            level=row.level,
            group=row.group,
            profile_join=JoinOp(row.profile_join),
            subject_join=JoinOp(row.subject_join),
        )

    @staticmethod
    def _operation_value(operation: Operation | str) -> str:
        return str(operation.value if isinstance(operation, Operation) else operation).strip().upper()

    @staticmethod
    def _entry_id(entry_id) -> UUID:
        return entry_id if isinstance(entry_id, UUID) else UUID(str(entry_id))
