# SPDX-License-Identifier: CC-BY-SA-4.0
"""Security-related ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Protocol

from auth.domain.request import AuthRequest
from auth.ports.audit import AuditLogger


class PasswordHasher(Protocol):
    algorithm: str
    version: int

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, stored_hash: str) -> bool: ...

    def needs_rehash(self, stored_hash: str) -> bool: ...


@dataclass(frozen=True)
class TokenValidationContext:
    issuer: str
    audience: str
    algorithms: frozenset[str]
    now: datetime


class TokenSigner(Protocol):
    def sign(self, claims: Mapping[str, Any], *, kid: str | None = None) -> str: ...

    def verify(self, token: str, expected: TokenValidationContext) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class SigningKey:
    kid: str
    material: str
    algorithm: str
    public_material: str | None = None


class KeyProvider(Protocol):
    def current(self) -> SigningKey: ...

    def get(self, kid: str) -> SigningKey | None: ...


class SecureRandom(Protocol):
    def token_urlsafe(self, nbytes: int = 32) -> str: ...

    def uuid4_hex(self) -> str: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int | None = None


class RateLimitPolicy(Protocol):
    def check(self, request: AuthRequest) -> RateLimitResult: ...


class AntiForgeryProtector(Protocol):
    def issue(self, secret_id: str) -> str: ...

    def verify(self, request: AuthRequest) -> bool: ...


class RedirectValidator(Protocol):
    def is_valid(self, target: str | None) -> bool: ...

    def sanitize(self, target: str | None) -> str: ...


def ttl_seconds(expires_at: datetime, now: datetime) -> int:
    remaining = expires_at - now
    return max(0, int(remaining / timedelta(seconds=1)))


__all__ = [
    "AuditLogger",
    "AntiForgeryProtector",
    "Clock",
    "KeyProvider",
    "PasswordHasher",
    "RateLimitPolicy",
    "RateLimitResult",
    "RedirectValidator",
    "SecureRandom",
    "SigningKey",
    "TokenSigner",
    "TokenValidationContext",
]
