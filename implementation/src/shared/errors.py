# SPDX-License-Identifier: CC-BY-SA-4.0
"""Eccezioni cross-cutting di MissionManager.

Questo modulo è il punto unico di definizione di tutte le eccezioni
applicative. Tutti gli altri layer (domain, application, infrastructure,
frontend) le importano da qui.

Gerarchia:
  MissionManagerError
    ├── ValidationError
    ├── NotFoundError
    ├── ForbiddenError
    │     └── AuthorizationError
    ├── AuthenticationError
    ├── ACLError
    ├── StatusTransitionError
    ├── OperationAbortedError
    ├── RateLimitExceededError
    ├── ExtensionLoadError
    └── ExtensionConflictError
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID


class MissionManagerError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(MissionManagerError):
    def __init__(self, message: str, field: Optional[str] = None) -> None:
        super().__init__(message)
        self.field = field


class NotFoundError(MissionManagerError):
    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[UUID | str] = None,
    ) -> None:
        super().__init__(message)
        self.resource_type = resource_type
        self.resource_id = resource_id


class ForbiddenError(MissionManagerError):
    """Accesso negato — soggetto autenticato ma senza permesso (HTTP 403)."""

    def __init__(self, message: str = "Accesso negato") -> None:
        super().__init__(message)


class AuthorizationError(ForbiddenError):
    """Livello ACL dell'operatore insufficiente per l'operazione richiesta."""


class AuthenticationError(MissionManagerError):
    """Token mancante, scaduto o non valido → HTTP 401."""

    def __init__(self, message: str = "Autenticazione fallita") -> None:
        super().__init__(message)


class ACLError(MissionManagerError):
    """Errore generico del sottosistema ACL (superclasse di Auth*)."""


class StatusTransitionError(MissionManagerError):
    def __init__(
        self,
        message: str,
        current_status: str,
        requested_status: str,
    ) -> None:
        super().__init__(message)
        self.current_status = current_status
        self.requested_status = requested_status


class OperationAbortedError(MissionManagerError):
    """Un plugin BEFORE_ hook ha impostato abort=True."""

    def __init__(
        self,
        message: str = "Operazione non consentita",
        abort_reason: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.abort_reason = abort_reason


class RateLimitExceededError(MissionManagerError):
    """Quota per (operatore, operazione) superata nella finestra corrente."""

    def __init__(
        self,
        message: str = "Troppe richieste",
        operation: Optional[str] = None,
        limit: Optional[int] = None,
        window: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.limit = limit
        self.window = window


class ExtensionLoadError(MissionManagerError):
    """Errore durante il caricamento o la verifica di un'estensione."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ExtensionConflictError(MissionManagerError):
    """Tentativo di registrare due estensioni con lo stesso nome."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
