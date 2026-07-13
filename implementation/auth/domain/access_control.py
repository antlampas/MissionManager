# SPDX-License-Identifier: CC-BY-SA-4.0
"""Common value objects for installable access-control models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol, TYPE_CHECKING

from auth.domain.errors import ValidationError
from auth.domain.types import AccountId

if TYPE_CHECKING:
    from auth.domain.identity import RequestIdentity
    from auth.domain.profile import AuthorizationProfile


class SubjectType(Enum):
    USER = "user"
    PUBLIC = "public"
    SERVICE = "service"


class Permission(Enum):
    ALLOW = "allow"
    DENY = "deny"


class Decision(Enum):
    ALLOWED = "allowed"
    DENIED = "denied"


class AccessControlCapability(Enum):
    ADMIN_API = "admin_api"
    CANDIDATE_RESOURCES = "candidate_resources"
    EXPLAIN = "explain"
    BOOTSTRAP_SEEDING = "bootstrap_seeding"


@dataclass(frozen=True)
class SubjectRef:
    type: SubjectType
    id: AccountId | None = None

    def __post_init__(self) -> None:
        if self.type is SubjectType.PUBLIC and self.id is not None:
            raise ValidationError("PUBLIC subject cannot have an id")
        if self.type in {SubjectType.USER, SubjectType.SERVICE} and self.id is None:
            raise ValidationError(f"{self.type.value} subject requires an id")

    @staticmethod
    def public() -> SubjectRef:
        return SubjectRef(SubjectType.PUBLIC, None)

    @staticmethod
    def user(account_id: AccountId) -> SubjectRef:
        return SubjectRef(SubjectType.USER, account_id)


@dataclass(frozen=True)
class ResourceRef:
    type: str
    id: str

    def __post_init__(self) -> None:
        if not self.type:
            raise ValidationError("resource type is required")
        if not self.id:
            raise ValidationError("resource id is required")


@dataclass(frozen=True)
class OperationSpec:
    name: str
    read_only: bool
    inheritable: bool = True
    protected: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValidationError("operation name is required")
        if self.protected and self.inheritable:
            raise ValidationError("protected operations cannot be inheritable")


@dataclass(frozen=True)
class AuthorizationContext:
    identity: RequestIdentity
    subject: SubjectRef
    profile: AuthorizationProfile
    operation: str
    operation_spec: OperationSpec
    resource: ResourceRef
    request_attrs: Mapping[str, object] = field(default_factory=dict)
    environment: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionTrace:
    decision: Decision
    reason: str
    model_id: str | None = None
    matched_artifacts: tuple[str, ...] = ()


class AccessControlModelExtension(Protocol):
    id: str
    capabilities: frozenset[AccessControlCapability]
    required_providers: frozenset[str]
    admin_operations: frozenset[str]

    def evaluate(self, context: AuthorizationContext) -> Decision: ...

    def candidate_resources(self, context: AuthorizationContext, resource_type: str) -> list[ResourceRef]: ...

    def explain(self, context: AuthorizationContext) -> DecisionTrace: ...

    def validate_config(self, settings: Mapping[str, object]) -> None: ...


SYSTEM_RESOURCE = ResourceRef("SYSTEM", "global")
TYPE_ROOT_ID = "*"
