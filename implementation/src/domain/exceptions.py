# SPDX-License-Identifier: CC-BY-SA-4.0
"""Re-export da shared.errors per compatibilità con import esistenti.

Tutto il codice nuovo deve importare direttamente da shared.errors.
Questo modulo esiste solo per non rompere gli import di domain/application
già presenti nel codebase.
"""
from ..shared.errors import (  # noqa: F401
    ACLError,
    AuthenticationError,
    AuthorizationError,
    ExtensionConflictError,
    ExtensionLoadError,
    ForbiddenError,
    MissionManagerError,
    NotFoundError,
    OperationAbortedError,
    RateLimitExceededError,
    StatusTransitionError,
    ValidationError,
)

__all__ = [
    "MissionManagerError",
    "ValidationError",
    "NotFoundError",
    "ForbiddenError",
    "AuthorizationError",
    "AuthenticationError",
    "ACLError",
    "StatusTransitionError",
    "OperationAbortedError",
    "RateLimitExceededError",
    "ExtensionLoadError",
    "ExtensionConflictError",
]
