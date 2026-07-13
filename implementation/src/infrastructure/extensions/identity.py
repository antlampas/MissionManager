# SPDX-License-Identifier: CC-BY-SA-4.0
"""Identity adapter per le estensioni MissionManager.

Fornisce un OperatorIdentityProvider che restituisce sempre lo stesso
operator_id fisso — utile per estensioni che devono operare per conto
di un operatore di sistema senza un contesto HTTP o CLI attivo.
"""
from __future__ import annotations

from uuid import UUID

from ...domain.entities import Person


class FixedOperatorIdentityAdapter:
    """IdentityAdapter che restituisce sempre l'operatore passato al costruttore.

    Usato dalle estensioni che hanno bisogno di un identity provider ma operano
    fuori da un contesto request (es. job in background, pipeline di dati).

    Esempio:
        idp = FixedOperatorIdentityAdapter(operator_id=system_user_id)
        result = mission_service.create(..., operator_id=idp.get_current_operator().id)
    """

    def __init__(self, operator_id: UUID, operator: Person | None = None) -> None:
        self._operator_id = operator_id
        self._operator = operator

    def get_current_operator(self) -> Person | None:
        return self._operator

    @property
    def operator_id(self) -> UUID:
        return self._operator_id
