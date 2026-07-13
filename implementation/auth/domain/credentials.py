# SPDX-License-Identifier: CC-BY-SA-4.0
"""Local credential domain model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from auth.domain.errors import ValidationError
from auth.domain.types import AccountId


@dataclass(frozen=True)
class LocalCredential:
    account_id: AccountId
    password_hash: str
    hash_algorithm: str
    hash_version: int
    failed_attempts: int
    locked_until: datetime | None
    password_changed_at: datetime
    must_change: bool

    def __post_init__(self) -> None:
        if not self.password_hash:
            raise ValidationError("password_hash is required")
        if not self.hash_algorithm:
            raise ValidationError("hash_algorithm is required")
        if self.hash_version < 0:
            raise ValidationError("hash_version cannot be negative")
        if self.failed_attempts < 0:
            raise ValidationError("failed_attempts cannot be negative")
        if self.locked_until is not None and self.locked_until.tzinfo is None:
            raise ValidationError("locked_until must be timezone-aware")
        if self.password_changed_at.tzinfo is None:
            raise ValidationError("password_changed_at must be timezone-aware")

    def is_locked(self, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValidationError("datetime must be timezone-aware")
        return self.locked_until is not None and self.locked_until > now

    def with_password(self, password_hash: str, algorithm: str, version: int, now: datetime, *, must_change: bool = False) -> LocalCredential:
        if now.tzinfo is None:
            raise ValidationError("datetime must be timezone-aware")
        return replace(
            self,
            password_hash=password_hash,
            hash_algorithm=algorithm,
            hash_version=version,
            failed_attempts=0,
            locked_until=None,
            password_changed_at=now,
            must_change=must_change,
        )

    def with_failure(self, locked_until: datetime | None = None) -> LocalCredential:
        if locked_until is not None and locked_until.tzinfo is None:
            raise ValidationError("locked_until must be timezone-aware")
        return replace(
            self,
            failed_attempts=self.failed_attempts + 1,
            locked_until=locked_until,
        )

    def reset_failures(self) -> LocalCredential:
        if self.failed_attempts == 0 and self.locked_until is None:
            return self
        return replace(self, failed_attempts=0, locked_until=None)
