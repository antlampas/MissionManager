# SPDX-License-Identifier: CC-BY-SA-4.0
"""Application DTOs that stay independent from transport runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from auth.domain.identity import RequestIdentity
from auth.domain.session import AuthSession
from auth.domain.types import AccountId, ClientRef, SessionId, TokenFamilyId


class RequestOutcomeKind(Enum):
    ALLOWED = "allowed"
    AUTHENTICATION_REQUIRED = "authentication_required"
    AUTHENTICATION_FAILED = "authentication_failed"
    AUTHORIZATION_DENIED = "authorization_denied"
    FORGERY_PROTECTION_FAILED = "forgery_protection_failed"
    RATE_LIMITED = "rate_limited"
    INVALID_REQUEST = "invalid_request"
    INTERACTION_REQUIRED = "interaction_required"


@dataclass(frozen=True)
class RequestOutcome:
    kind: RequestOutcomeKind
    identity: RequestIdentity | None = None
    retry_after_seconds: int | None = None
    return_target: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AuthContext:
    origin: str = "unknown"
    correlation_id: str | None = None
    return_target: str | None = None
    issue_session: bool = True
    issue_tokens: bool = False
    issue_refresh_token: bool = False
    current_session_id: SessionId | None = None
    client_ref: ClientRef | None = None


@dataclass(frozen=True)
class AccessToken:
    value: str
    jti: str
    expires_at: datetime


@dataclass(frozen=True)
class RefreshToken:
    value: str
    id: str
    family_id: TokenFamilyId
    expires_at: datetime


@dataclass(frozen=True)
class TokenPair:
    access_token: AccessToken
    refresh_token: RefreshToken | None = None


@dataclass(frozen=True)
class AuthenticationResult:
    account_id: AccountId
    identity: RequestIdentity
    session: AuthSession | None = None
    access_token: AccessToken | None = None
    refresh_token: RefreshToken | None = None
    must_change_password: bool = False
    return_target: str | None = None


class OidcIntent(Enum):
    LOGIN = "login"
    LINK = "link"
    FIRST_ADMIN = "first_admin"


@dataclass(frozen=True)
class OidcStartResult:
    authorization_url: str
    state: str
    expires_at: datetime


@dataclass(frozen=True)
class OidcAccountResolution:
    account_id: AccountId
    identity_provider_id: str
    profile_was_mapped: bool


@dataclass(frozen=True)
class LogoutResult:
    session_revoked: bool = False
    token_revoked: bool = False
    return_target: str | None = None
