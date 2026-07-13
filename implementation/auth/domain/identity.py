# SPDX-License-Identifier: CC-BY-SA-4.0
"""External identity and resolved request identity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping

from auth.domain.access_control import SubjectRef
from auth.domain.errors import ValidationError
from auth.domain.types import AccountId, ExternalIdentityId, SessionId


class AuthMethod(Enum):
    LOCAL_PASSWORD = "local_password"
    OIDC = "oidc"
    SESSION = "session"
    ACCESS_TOKEN = "access_token"
    ASSERTED = "asserted"


@dataclass(frozen=True)
class ExternalIdentity:
    id: ExternalIdentityId
    account_id: AccountId
    provider: str
    issuer: str
    subject: str
    email: str | None
    display_name: str | None
    linked_at: datetime

    def __post_init__(self) -> None:
        if not self.provider:
            raise ValidationError("provider is required")
        if not self.issuer:
            raise ValidationError("issuer is required")
        if not self.subject:
            raise ValidationError("subject is required")
        if self.linked_at.tzinfo is None:
            raise ValidationError("linked_at must be timezone-aware")


@dataclass(frozen=True)
class RequestIdentity:
    subject: SubjectRef
    account_id: AccountId | None
    auth_method: AuthMethod | None
    authenticated_at: datetime | None
    session_id: SessionId | None = None
    token_id: str | None = None

    def __post_init__(self) -> None:
        if self.authenticated_at is not None and self.authenticated_at.tzinfo is None:
            raise ValidationError("authenticated_at must be timezone-aware")
        if self.account_id is None and self.auth_method is not None:
            raise ValidationError("anonymous identity cannot have an auth method")

    @staticmethod
    def anonymous() -> RequestIdentity:
        return RequestIdentity(
            subject=SubjectRef.public(),
            account_id=None,
            auth_method=None,
            authenticated_at=None,
        )


@dataclass(frozen=True)
class OidcClaims:
    issuer: str
    subject: str
    audience: str
    expires_at: datetime
    nonce: str
    email: str | None = None
    display_name: str | None = None
    extra_claims: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.issuer or not self.subject or not self.audience:
            raise ValidationError("issuer, subject and audience are required")
        if self.expires_at.tzinfo is None:
            raise ValidationError("expires_at must be timezone-aware")


@dataclass(frozen=True)
class OidcTransaction:
    provider: str
    state: str
    nonce: str
    pkce_verifier: str
    intent: str
    created_at: datetime
    expires_at: datetime
    return_target: str | None = None
    origin_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.provider or not self.state or not self.nonce or not self.pkce_verifier:
            raise ValidationError("provider, state, nonce and pkce_verifier are required")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValidationError("OIDC transaction timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValidationError("OIDC transaction must expire after creation")
