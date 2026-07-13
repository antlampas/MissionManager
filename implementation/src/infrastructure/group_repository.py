# SPDX-License-Identifier: CC-BY-SA-4.0
from abc import abstractmethod
from uuid import UUID

from ..domain.entities import Group
from .base import RepositoryAdapter


class GroupRepositoryAdapter(RepositoryAdapter[Group]):
    """Base astratta per la persistenza di Group.

    Stesse famiglie di implementazioni di PersonRepositoryAdapter
    (local SQLAlchemy oppure OIDC), selezionabili via PERSON_BACKEND.
    """

    @abstractmethod
    def add_member(self, group_id: UUID, person_id: UUID) -> None: ...

    @abstractmethod
    def remove_member(self, group_id: UUID, person_id: UUID) -> None: ...
