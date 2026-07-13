# SPDX-License-Identifier: CC-BY-SA-4.0
"""MissionManager adapter surface for the external ``acl`` package.

Il motore ACL riusabile vive nel package top-level :mod:`acl`. Questo modulo
mantiene i nomi storici importati dal dominio MissionManager e normalizza i
concetti applicativi locali (ResourceType, catalogo operazioni, UUID) verso il
modello esterno.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Optional
from uuid import UUID

from acl.domain import (
    ACLEntry as _ExternalACLEntry,
    ACLEntryInvariants,
    ACLValidationError,
    ANON_SENTINEL,
    PUBLIC_GROUP,
    SYSTEM_ID as SYSTEM_GLOBAL_ID,
    TYPE_ROOT_ID,
    JoinOp,
    OperationSpec,
    Permission,
    entry_matches,
)
from acl.domain import Profile as _ExternalProfile
from acl.domain import ResourceRef as _ExternalResourceRef
from acl.domain import SubjectRef as _ExternalSubjectRef
from acl.domain import SubjectType
from acl.infrastructure.operations import StaticOperationCatalog

from .enums import ResourceType
from .exceptions import ValidationError


class Operation(StrEnum):
    """Catalogo applicativo delle operazioni autorizzabili."""

    VIEW = "VIEW"
    LIST = "LIST"
    EDIT = "EDIT"
    DELETE = "DELETE"
    ASSIGN = "ASSIGN"
    UPDATE_STATUS = "UPDATE_STATUS"
    AWARD_BADGE = "AWARD_BADGE"
    MANAGE_MEMBERS = "MANAGE_MEMBERS"
    CREATE_ASSIGNMENT = "CREATE_ASSIGNMENT"
    CREATE_MISSION = "CREATE_MISSION"
    CREATE_BADGE = "CREATE_BADGE"
    CREATE_PERSON = "CREATE_PERSON"
    CREATE_GROUP = "CREATE_GROUP"
    MANAGE_PROFILES = "MANAGE_PROFILES"
    EXECUTE = "EXECUTE"
    MANAGE_ACL = "MANAGE_ACL"

    @property
    def read_only(self) -> bool:
        return self in {Operation.VIEW, Operation.LIST}


NON_INHERITABLE_OPERATIONS = frozenset(
    {
        Operation.CREATE_MISSION,
        Operation.CREATE_BADGE,
        Operation.CREATE_PERSON,
        Operation.CREATE_GROUP,
        Operation.MANAGE_PROFILES,
        Operation.EXECUTE,
        Operation.MANAGE_ACL,
    }
)


def _operation_name(operation: Operation | str) -> str:
    return str(operation.value if isinstance(operation, Operation) else operation).strip().upper()


_MISSIONMANAGER_OPERATION_SPECS = (
    OperationSpec(Operation.VIEW.value, read_only=True, inheritable=True),
    OperationSpec(Operation.LIST.value, read_only=True, inheritable=True),
    OperationSpec(Operation.EDIT.value, read_only=False, inheritable=True),
    OperationSpec(Operation.DELETE.value, read_only=False, inheritable=True),
    OperationSpec(Operation.ASSIGN.value, read_only=False, inheritable=True),
    OperationSpec(Operation.UPDATE_STATUS.value, read_only=False, inheritable=True),
    OperationSpec(Operation.AWARD_BADGE.value, read_only=False, inheritable=True),
    OperationSpec(Operation.MANAGE_MEMBERS.value, read_only=False, inheritable=True),
    OperationSpec(Operation.CREATE_ASSIGNMENT.value, read_only=False, inheritable=True),
    OperationSpec(Operation.CREATE_MISSION.value, read_only=False, inheritable=False),
    OperationSpec(Operation.CREATE_BADGE.value, read_only=False, inheritable=False),
    OperationSpec(Operation.CREATE_PERSON.value, read_only=False, inheritable=False),
    OperationSpec(Operation.CREATE_GROUP.value, read_only=False, inheritable=False),
    OperationSpec(Operation.MANAGE_PROFILES.value, read_only=False, inheritable=False, protected=True),
    OperationSpec(Operation.EXECUTE.value, read_only=False, inheritable=False, protected=True),
    OperationSpec(Operation.MANAGE_ACL.value, read_only=False, inheritable=False, protected=True),
)


def missionmanager_operation_catalog() -> StaticOperationCatalog:
    """Return the operation catalog required by the reusable ACL engine."""

    return StaticOperationCatalog(_MISSIONMANAGER_OPERATION_SPECS)


def _resource_type_value(value: ResourceType | str) -> str:
    if isinstance(value, ResourceType):
        return value.value
    raw = str(value.value if hasattr(value, "value") else value).strip().upper()
    if raw.startswith("RESOURCETYPE."):
        raw = raw.rsplit(".", 1)[-1]
    return raw


@dataclass(frozen=True)
class ResourceRef:
    """Resource reference accepted by both MissionManager and ``acl`` ports."""

    type: ResourceType | str
    id: UUID | str

    def __post_init__(self) -> None:
        raw_type = _resource_type_value(self.type)
        try:
            normalized_type: ResourceType | str = ResourceType(raw_type)
        except ValueError:
            normalized_type = raw_type
        resource_id = str(self.id).strip()
        if not resource_id:
            raise ValidationError("resource id is required", field="resource_id")
        object.__setattr__(self, "type", normalized_type)
        object.__setattr__(self, "id", resource_id)

    def key(self) -> str:
        return str(self.id)

    @property
    def type_value(self) -> str:
        return _resource_type_value(self.type)

    @property
    def is_system(self) -> bool:
        return self.type_value == ResourceType.SYSTEM.value and self.key() == SYSTEM_GLOBAL_ID

    @property
    def is_type_root(self) -> bool:
        return self.key() == TYPE_ROOT_ID

    @property
    def is_concrete(self) -> bool:
        return not self.is_system and not self.is_type_root

    @staticmethod
    def type_root(resource_type: ResourceType | str) -> "ResourceRef":
        return ResourceRef(resource_type, TYPE_ROOT_ID)

    @staticmethod
    def system() -> "ResourceRef":
        return ResourceRef(ResourceType.SYSTEM, SYSTEM_GLOBAL_ID)


SYSTEM_RESOURCE = ResourceRef.system()


@dataclass(frozen=True)
class SubjectRef:
    """Subject reference with MissionManager exceptions and ACL semantics."""

    type: SubjectType
    id: Optional[str] = None

    def __post_init__(self) -> None:
        try:
            subject = _ExternalSubjectRef(self.type, self.id)
        except ValueError as exc:
            raise ValidationError(str(exc), field="subject_id") from exc
        object.__setattr__(self, "type", subject.type)
        object.__setattr__(self, "id", subject.id)

    @staticmethod
    def public() -> "SubjectRef":
        return SubjectRef(SubjectType.PUBLIC)

    @staticmethod
    def user(principal_id: UUID | str) -> "SubjectRef":
        return SubjectRef(SubjectType.USER, str(principal_id))


@dataclass(frozen=True)
class Profile:
    """Authorization profile stored on ``Person`` and consumed by ``acl``."""

    level: int = ANON_SENTINEL
    groups: frozenset[str] = field(default_factory=frozenset)
    version: int | None = None

    def __post_init__(self) -> None:
        try:
            level = int(self.level)
        except (TypeError, ValueError) as exc:
            raise ValidationError("profile level must be an integer", field="acl_level") from exc
        if level < 0 or level > ANON_SENTINEL:
            raise ValidationError(
                "profile level must be between 0 and ANON_SENTINEL",
                field="acl_level",
            )
        normalized = frozenset(
            str(group).strip() for group in (self.groups or ()) if str(group).strip()
        ) | {PUBLIC_GROUP}
        object.__setattr__(self, "level", level)
        object.__setattr__(self, "groups", normalized)
        object.__setattr__(self, "version", self.version)

    @staticmethod
    def anonymous() -> "Profile":
        return Profile(level=ANON_SENTINEL, groups=frozenset())

    def stored_groups(self) -> list[str]:
        return sorted(self.groups - {PUBLIC_GROUP})


@dataclass(frozen=True)
class AclEntry:
    """Compatibility entry whose invariants/matching are delegated to ``acl``."""

    id: UUID | str
    subject: SubjectRef
    resource: ResourceRef
    operation: Operation | str
    permission: Permission
    level: Optional[int] = None
    group: Optional[str] = None
    profile_join: JoinOp = JoinOp.OR
    subject_join: JoinOp = JoinOp.AND

    def __post_init__(self) -> None:
        try:
            operation = Operation(_operation_name(self.operation))
        except ValueError:
            operation = _operation_name(self.operation)
        group = None if self.group is None else str(self.group).strip()
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "permission", Permission(self.permission))
        object.__setattr__(self, "profile_join", JoinOp(self.profile_join))
        object.__setattr__(self, "subject_join", JoinOp(self.subject_join))
        object.__setattr__(self, "group", group or None)

    def validate(self) -> None:
        try:
            spec = missionmanager_operation_catalog().require(_operation_name(self.operation))
            ACLEntryInvariants().validate(self.to_external(), spec)
        except (ACLValidationError, ValueError) as exc:
            raise ValidationError(str(exc)) from exc

    def matches(self, principal_id: Optional[UUID], profile: Profile) -> bool:
        subject = (
            _ExternalSubjectRef.public()
            if principal_id is None
            else _ExternalSubjectRef.user(str(principal_id))
        )
        return entry_matches(self.to_external(), subject, to_external_profile(profile))

    def to_external(self) -> _ExternalACLEntry:
        return _ExternalACLEntry(
            id=str(self.id),
            subject=to_external_subject(self.subject),
            resource=to_external_resource(self.resource),
            operation=_operation_name(self.operation),
            permission=self.permission,
            level=self.level,
            group=self.group,
            profile_join=self.profile_join,
            subject_join=self.subject_join,
        )


def to_external_resource(resource: ResourceRef | _ExternalResourceRef) -> _ExternalResourceRef:
    if isinstance(resource, _ExternalResourceRef):
        return resource
    return _ExternalResourceRef(resource.type_value, resource.key())


def to_external_subject(subject: SubjectRef | _ExternalSubjectRef) -> _ExternalSubjectRef:
    if isinstance(subject, _ExternalSubjectRef):
        return subject
    return _ExternalSubjectRef(subject.type, subject.id)


def to_external_profile(profile: Profile | _ExternalProfile) -> _ExternalProfile:
    if isinstance(profile, _ExternalProfile):
        return profile
    return profile


def from_external_resource(resource: ResourceRef | _ExternalResourceRef) -> ResourceRef:
    if isinstance(resource, ResourceRef):
        return resource
    return ResourceRef(resource.type, resource.id)


def from_external_subject(subject: SubjectRef | _ExternalSubjectRef) -> SubjectRef:
    if isinstance(subject, SubjectRef):
        return subject
    return SubjectRef(subject.type, subject.id)
