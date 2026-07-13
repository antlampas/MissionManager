# SPDX-License-Identifier: CC-BY-SA-4.0
"""Domain and application error hierarchy."""

from __future__ import annotations


class AuthError(Exception):
    """Base class for Auth failures."""


class ConfigurationError(AuthError):
    """The runtime is misconfigured and must fail closed."""


class ValidationError(AuthError):
    """Input or state violates an Auth invariant."""


class AuthenticationError(AuthError):
    """Authentication failed without leaking whether subject or secret was wrong."""


class AuthorizationDenied(AuthError):
    """The active access-control model denied the operation."""


class ForgeryProtectionError(AuthError):
    """Anti-forgery validation failed."""


class RateLimitExceeded(AuthError):
    """A rate limit blocked the operation."""

    def __init__(self, message: str = "rate limit exceeded", retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class SetupRequired(AuthError):
    """The Auth runtime must be bootstrapped before ordinary use."""


class PasswordPolicyViolation(ValidationError):
    """A password does not satisfy the configured creation/change policy."""
