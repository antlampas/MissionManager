# SPDX-License-Identifier: CC-BY-SA-4.0
from abc import ABC, abstractmethod
from contextlib import nullcontext

from ...domain.entities import Person
from ...domain.repositories import PersonRepository


class OperatorIdentityAdapter(ABC):
    """Base astratta per la risoluzione dell'identità dell'operatore corrente.

    Tre implementazioni concrete (una per frontend):
    - RestOperatorIdentityAdapter: valida JWT/sessione HTTP
    - WebOperatorIdentityAdapter: legge la sessione Quart
    - CliOperatorIdentityAdapter: legge MISSIONMANAGER_OPERATOR_ID

    Tutte chiamano person_repo.get(operator_id) per materializzare
    il profilo completo con il Profile ACL.
    """

    def __init__(self, person_repo: PersonRepository, uow=None) -> None:
        self._person_repo = person_repo
        self._uow = uow

    def _get_person(self, operator_id):
        context = self._uow.transaction() if self._uow is not None else nullcontext()
        with context:
            return self._person_repo.get(operator_id)

    @abstractmethod
    def get_current_operator(self) -> Person: ...
