# SPDX-License-Identifier: CC-BY-SA-4.0
"""Canonical request DTOs, independent from any web or RPC runtime."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from auth.domain.access_control import ResourceRef
from auth.domain.errors import ValidationError


class CredentialKind(Enum):
    NONE = "none"
    SESSION_ID = "session_id"
    ACCESS_TOKEN = "access_token"
    LOCAL_SECRET = "local_secret"
    OIDC_CODE = "oidc_code"
    ASSERTED_ACCOUNT = "asserted_account"


class CredentialMode(Enum):
    AMBIENT = "ambient"
    EXPLICIT = "explicit"
    ASSERTED = "asserted"


@dataclass(frozen=True)
class RequestOrigin:
    name: str
    kind: str
    trusted: bool
    client_ref: str | None = None
    address: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValidationError("origin name is required")
        if not self.kind:
            raise ValidationError("origin kind is required")


@dataclass(frozen=True)
class CredentialPresentation:
    kind: CredentialKind
    mode: CredentialMode
    value_ref: str | None = None
    issuer: str | None = None

    def __post_init__(self) -> None:
        if self.kind is CredentialKind.NONE and self.value_ref is not None and self.issuer != "anti_forgery":
            raise ValidationError("NONE credential cannot carry a value")
        if self.kind is CredentialKind.ASSERTED_ACCOUNT and self.mode is not CredentialMode.ASSERTED:
            raise ValidationError("asserted account credentials must use ASSERTED mode")


@dataclass(frozen=True)
class ProtectionRequirements:
    allow_anonymous: bool
    require_active_account: bool = True
    require_anti_forgery: bool = False
    require_return_target: bool = False


@dataclass(frozen=True)
class AuthRequest:
    id: str
    origin: RequestOrigin
    credential_presentations: tuple[CredentialPresentation, ...]
    operation: str | None
    resource: ResourceRef | None
    mutation: bool
    protection: ProtectionRequirements
    return_target: str | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValidationError("request id is required")
        if not self.credential_presentations:
            object.__setattr__(
                self,
                "credential_presentations",
                (CredentialPresentation(CredentialKind.NONE, CredentialMode.EXPLICIT),),
            )
        if any(c.kind is CredentialKind.ASSERTED_ACCOUNT for c in self.credential_presentations) and not self.origin.trusted:
            raise ValidationError("asserted account requires a trusted origin")
        ambient = any(c.mode is CredentialMode.AMBIENT for c in self.credential_presentations)
        if self.mutation and ambient and not self.protection.require_anti_forgery:
            object.__setattr__(
                self,
                "protection",
                replace(self.protection, require_anti_forgery=True),
            )
        if (self.operation is None) != (self.resource is None):
            raise ValidationError("operation and resource must be provided together")


@dataclass(frozen=True)
class RequestCheck:
    key: str
    operation: str
    resource: ResourceRef
    mutation: bool
    allow_anonymous: bool = False
