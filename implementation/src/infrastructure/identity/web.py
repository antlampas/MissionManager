# SPDX-License-Identifier: CC-BY-SA-4.0
"""WebOperatorIdentityAdapter — legge l'identità dalla sessione Quart.

Il login handler (locale o OIDC callback) scrive 'operator_id' (str UUID)
nella sessione Quart firmata con secret_key.  Nessuna validazione JWT qui:
l'integrità è garantita dalla firma del cookie di sessione.

Solleva AuthenticationError (→ HTTP 401 / redirect /login) se la sessione
non contiene un operator_id valido.
"""
from __future__ import annotations

from uuid import UUID

from quart import session

from ...infrastructure.identity.base import OperatorIdentityAdapter
from ...domain.entities import Person
from ...domain.exceptions import AuthenticationError
from ...domain.repositories import PersonRepository


class WebOperatorIdentityAdapter(OperatorIdentityAdapter):

    SESSION_KEY = "operator_id"

    def __init__(self, person_repo: PersonRepository, uow=None) -> None:
        super().__init__(person_repo, uow=uow)

    def get_current_operator(self) -> Person:
        raw = session.get(self.SESSION_KEY)
        if not raw:
            raise AuthenticationError("Sessione non autenticata")
        try:
            operator_id = UUID(raw)
        except (ValueError, AttributeError) as exc:
            raise AuthenticationError(
                "operator_id nella sessione non è un UUID valido"
            ) from exc
        return self._get_person(operator_id)
