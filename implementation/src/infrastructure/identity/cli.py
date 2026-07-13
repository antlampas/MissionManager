# SPDX-License-Identifier: CC-BY-SA-4.0
"""CliOperatorIdentityAdapter — legge l'identità dalla variabile d'ambiente o dalla config."""
from __future__ import annotations

import os
from typing import Optional
from uuid import UUID

from ...infrastructure.identity.base import OperatorIdentityAdapter
from ...domain.entities import Person
from ...domain.exceptions import ACLError, NotFoundError
from ...domain.repositories import PersonRepository

_ENV_VAR = "MISSIONMANAGER_OPERATOR_ID"


class CliOperatorIdentityAdapter(OperatorIdentityAdapter):
    """Resolves the operator from MISSIONMANAGER_OPERATOR_ID env var (or a fixed UUID
    passed at construction time).  Used by the CLI bootstrap.

    If identity_mode == "anonymous", get_current_operator() returns None:
    i comandi valutano allora il profilo anonimo implicito (DESIGN §10) e
    passano solo le concessioni PUBLIC di sola lettura.
    """

    def __init__(
        self,
        person_repo: PersonRepository,
        operator_id: Optional[UUID] = None,
        identity_mode: str = "anonymous",
        uow=None,
    ) -> None:
        super().__init__(person_repo, uow=uow)
        self._operator_id = operator_id
        self._identity_mode = identity_mode

    def get_current_operator(self) -> Optional[Person]:
        if self._identity_mode == "anonymous":
            return None

        uid = self._operator_id or self._from_env()
        if uid is None:
            raise ACLError(
                f"identity_mode=user ma {_ENV_VAR} non è impostata"
            )
        try:
            return self._get_person(uid)
        except NotFoundError as exc:
            raise ACLError(
                f"Operatore {uid} non trovato nel repository"
            ) from exc

    @staticmethod
    def _from_env() -> Optional[UUID]:
        raw = os.environ.get(_ENV_VAR)
        if raw:
            try:
                return UUID(raw)
            except ValueError:
                return None
        return None
