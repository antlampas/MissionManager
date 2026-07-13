# SPDX-License-Identifier: CC-BY-SA-4.0
"""Opaque server-side session metadata."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from auth.domain.errors import ValidationError
from auth.domain.identity import AuthMethod
from auth.domain.types import AccountId, SessionId


@dataclass(frozen=True)
class AuthSession:
    id: SessionId
    account_id: AccountId
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    auth_method: AuthMethod
    authz_version: int
    anti_forgery_secret_id: str | None

    def __post_init__(self) -> None:
        for name in ("created_at", "last_seen_at", "expires_at"):
            value = getattr(self, name)
            if value.tzinfo is None:
                raise ValidationError(f"{name} must be timezone-aware")
        if self.revoked_at is not None and self.revoked_at.tzinfo is None:
            raise ValidationError("revoked_at must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValidationError("session must expire after creation")
        if self.authz_version < 0:
            raise ValidationError("authz_version cannot be negative")

    def is_valid(self, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValidationError("datetime must be timezone-aware")
        return self.revoked_at is None and self.expires_at > now

    def touch(self, now: datetime) -> AuthSession:
        if now.tzinfo is None:
            raise ValidationError("datetime must be timezone-aware")
        return replace(self, last_seen_at=now)

    def revoke(self, now: datetime) -> AuthSession:
        if now.tzinfo is None:
            raise ValidationError("datetime must be timezone-aware")
        if self.revoked_at is not None:
            return self
        return replace(self, revoked_at=now)
