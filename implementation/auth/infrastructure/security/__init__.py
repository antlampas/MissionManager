# SPDX-License-Identifier: CC-BY-SA-4.0
"""Security adapters."""

from auth.infrastructure.security.audit import RepositoryAuditLogger
from auth.infrastructure.security.clock import FrozenClock, SystemClock
from auth.infrastructure.security.password import Argon2idPasswordHasher, BcryptPasswordHasher, Pbkdf2PasswordHasher
from auth.infrastructure.security.protections import HmacAntiForgeryProtector, ReturnTargetRedirectValidator
from auth.infrastructure.security.random import SecretsSecureRandom
from auth.infrastructure.security.rate_limit import InMemoryRateLimitPolicy, NoopRateLimitPolicy
from auth.infrastructure.security.token import HmacTokenSigner

__all__ = [
    "Argon2idPasswordHasher",
    "BcryptPasswordHasher",
    "FrozenClock",
    "HmacAntiForgeryProtector",
    "HmacTokenSigner",
    "InMemoryRateLimitPolicy",
    "NoopRateLimitPolicy",
    "Pbkdf2PasswordHasher",
    "RepositoryAuditLogger",
    "ReturnTargetRedirectValidator",
    "SecretsSecureRandom",
    "SystemClock",
]
