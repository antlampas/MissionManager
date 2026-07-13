# SPDX-License-Identifier: CC-BY-SA-4.0
"""Token metadata kept by the pure domain."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from auth.domain.access_control import SubjectRef
from auth.domain.errors import ValidationError
from auth.domain.identity import AuthMethod
from auth.domain.types import AccountId, RefreshTokenId, TokenFamilyId


@dataclass(frozen=True)
class TokenPrincipal:
    account_id: AccountId
    subject: SubjectRef
    jti: str
    issuer: str
    audience: str
    expires_at: datetime
    authz_version: int
    auth_method: AuthMethod

    def __post_init__(self) -> None:
        if not self.jti or not self.issuer or not self.audience:
            raise ValidationError("jti, issuer and audience are required")
        if self.expires_at.tzinfo is None:
            raise ValidationError("expires_at must be timezone-aware")
        if self.authz_version < 0:
            raise ValidationError("authz_version cannot be negative")


@dataclass(frozen=True)
class RefreshTokenRecord:
    id: RefreshTokenId
    family_id: TokenFamilyId
    account_id: AccountId
    token_hash: str
    issued_at: datetime
    expires_at: datetime
    rotated_at: datetime | None
    revoked_at: datetime | None

    def __post_init__(self) -> None:
        if not self.token_hash:
            raise ValidationError("token_hash is required")
        for name in ("issued_at", "expires_at"):
            value = getattr(self, name)
            if value.tzinfo is None:
                raise ValidationError(f"{name} must be timezone-aware")
        if self.rotated_at is not None and self.rotated_at.tzinfo is None:
            raise ValidationError("rotated_at must be timezone-aware")
        if self.revoked_at is not None and self.revoked_at.tzinfo is None:
            raise ValidationError("revoked_at must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValidationError("refresh token must expire after issue")

    def active(self, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValidationError("datetime must be timezone-aware")
        return self.rotated_at is None and self.revoked_at is None and self.expires_at > now

    def rotate(self, now: datetime) -> RefreshTokenRecord:
        if now.tzinfo is None:
            raise ValidationError("datetime must be timezone-aware")
        if self.rotated_at is not None:
            return self
        return replace(self, rotated_at=now)

    def revoke(self, now: datetime) -> RefreshTokenRecord:
        if now.tzinfo is None:
            raise ValidationError("datetime must be timezone-aware")
        if self.revoked_at is not None:
            return self
        return replace(self, revoked_at=now)
