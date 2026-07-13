# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable
from uuid import UUID


@dataclass
class LocalCredential:
    """Credenziale locale di un Person (backend 'local').

    Oltre all'hash bcrypt della password conserva lo stato di hardening:
    - ``failed_attempts`` / ``locked_until`` alimentano il blocco temporaneo
      dell'account dopo troppi tentativi di login falliti;
    - ``must_change_password`` forza il cambio password al primo accesso (es.
      password impostata da un amministratore per un altro operatore).
    """

    person_id: UUID
    hashed_password: str
    failed_attempts: int = 0
    locked_until: Optional[datetime] = None
    must_change_password: bool = False


@runtime_checkable
class CredentialRepository(Protocol):
    """Porta per archiviare le credenziali locali (hash bcrypt + stato lockout).

    Implementata da SqlAlchemyCredentialRepository (backend locale).
    Non usata in modalità OIDC pura.
    """

    def get(self, person_id: UUID) -> Optional[LocalCredential]: ...
    def save(self, credential: LocalCredential) -> None: ...
    def delete(self, person_id: UUID) -> bool: ...
