# SPDX-License-Identifier: CC-BY-SA-4.0
from abc import abstractmethod
from typing import Optional
from uuid import UUID

from ..domain.entities import Person
from .base import RepositoryAdapter


class PersonRepositoryAdapter(RepositoryAdapter[Person]):
    """Base astratta per la persistenza di Person.

    Due famiglie di implementazioni concrete selezionabili via config:
    - SqlAlchemyPersonRepository (PERSON_BACKEND=local)
    - OidcPersonRepository (PERSON_BACKEND=oidc)
    """

    @abstractmethod
    def get_by_group(self, group_id: UUID) -> list[Person]: ...

    @abstractmethod
    def get_by_nickname(self, nickname: str) -> Optional[Person]: ...
