# SPDX-License-Identifier: CC-BY-SA-4.0
"""LocalOidcPersonRepository — persone locali con identita OIDC collegate."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from ...domain.entities import Person
from ...infrastructure.person_repository import PersonRepositoryAdapter
from ..repositories.external_identity_repository import SqlAlchemyExternalIdentityRepository


class LocalOidcPersonRepository(PersonRepositoryAdapter):
    """Decora il repository locale aggiungendo il mapping ``sub`` OIDC -> Person.

    Usato quando l'autenticazione e' OIDC ma l'anagrafica resta applicativa
    locale, come in PhotoGallery: il login non richiede admin API dell'IdP.
    """

    def __init__(
        self,
        delegate: PersonRepositoryAdapter,
        identity_repo: SqlAlchemyExternalIdentityRepository,
        provider: str,
    ) -> None:
        self._delegate = delegate
        self._identities = identity_repo
        self._provider = provider

    def resolve_external_subject(self, subject: str) -> UUID:
        return self._identities.internal_id(self._provider, "person", str(subject))

    def bind_external_subject(self, subject: str, person_id: UUID) -> None:
        self._identities.bind(self._provider, "person", str(subject), person_id)

    def get(self, id: UUID) -> Person:
        return self._delegate.get(id)

    def list(self, filters: dict) -> list[Person]:
        return self._delegate.list(filters)

    def save(self, entity: Person) -> Person:
        return self._delegate.save(entity)

    def delete(self, id: UUID) -> bool:
        deleted = self._delegate.delete(id)
        if deleted:
            self._identities.delete(self._provider, "person", id)
        return deleted

    def exists(self, id: UUID) -> bool:
        return self._delegate.exists(id)

    def get_by_group(self, group_id: UUID) -> list[Person]:
        return self._delegate.get_by_group(group_id)

    def get_by_nickname(self, nickname: str) -> Optional[Person]:
        return self._delegate.get_by_nickname(nickname)
