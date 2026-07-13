# SPDX-License-Identifier: CC-BY-SA-4.0
"""Account aggregate and related enumerations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from auth.domain.errors import AuthenticationError, ValidationError
from auth.domain.types import AccountId, ProfileId


class AccountStatus(Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


class AccountKind(Enum):
    HUMAN = "human"
    SERVICE = "service"


class AccountFlag(Enum):
    MUST_CHANGE_PASSWORD = "must_change_password"
    BOOTSTRAP_SUPERUSER = "bootstrap_superuser"
    MFA_REQUIRED = "mfa_required"


@dataclass(frozen=True)
class Account:
    id: AccountId
    username: str | None
    email: str | None
    kind: AccountKind
    status: AccountStatus
    profile_id: ProfileId
    authz_version: int
    flags: frozenset[AccountFlag]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.username is None and self.email is None:
            raise ValidationError("account requires username or email")
        if self.authz_version < 0:
            raise ValidationError("authz_version cannot be negative")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValidationError("account timestamps must be timezone-aware")

    def is_active(self) -> bool:
        return self.status is AccountStatus.ACTIVE

    def require_active(self) -> None:
        if self.status is not AccountStatus.ACTIVE:
            raise AuthenticationError("authentication failed")

    def mark_disabled(self, now: datetime) -> Account:
        self._require_aware(now)
        if self.status is AccountStatus.DELETED:
            raise ValidationError("deleted accounts cannot be disabled")
        if self.status is AccountStatus.DISABLED:
            return self
        return replace(
            self,
            status=AccountStatus.DISABLED,
            authz_version=self.authz_version + 1,
            updated_at=now,
        )

    def mark_deleted(self, now: datetime) -> Account:
        self._require_aware(now)
        if self.status is AccountStatus.DELETED:
            return self
        return replace(
            self,
            status=AccountStatus.DELETED,
            authz_version=self.authz_version + 1,
            updated_at=now,
        )

    def with_profile(self, profile_id: ProfileId, now: datetime) -> Account:
        self._require_aware(now)
        if profile_id == self.profile_id:
            return self
        return replace(
            self,
            profile_id=profile_id,
            authz_version=self.authz_version + 1,
            updated_at=now,
        )

    def with_flags(self, flags: frozenset[AccountFlag], now: datetime) -> Account:
        self._require_aware(now)
        if flags == self.flags:
            return self
        return replace(
            self,
            flags=frozenset(flags),
            authz_version=self.authz_version + 1,
            updated_at=now,
        )

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None:
            raise ValidationError("datetime must be timezone-aware")
