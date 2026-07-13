# SPDX-License-Identifier: CC-BY-SA-4.0
from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

T = TypeVar("T")


class RepositoryAdapter(ABC, Generic[T]):
    """Base astratta per tutti gli adapter di repository.

    Le implementazioni concrete estendono questa classe e iniettano
    il meccanismo di persistenza nel costruttore (es. SQLAlchemy Session).
    """

    @abstractmethod
    def get(self, id: UUID) -> T: ...

    @abstractmethod
    def list(self, filters: dict) -> list[T]: ...

    @abstractmethod
    def save(self, entity: T) -> T: ...

    @abstractmethod
    def delete(self, id: UUID) -> bool: ...

    @abstractmethod
    def exists(self, id: UUID) -> bool: ...
