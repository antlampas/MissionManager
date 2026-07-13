# SPDX-License-Identifier: CC-BY-SA-4.0
"""Persistenza del mapping tra ID del dominio e subject OIDC opachi."""
from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from .models import ExternalIdentityRow


class SqlAlchemyExternalIdentityRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def external_id(
        self, provider: str, resource_type: str, internal_id: UUID
    ) -> str | None:
        row = (
            self._s.query(ExternalIdentityRow)
            .filter_by(
                provider=provider,
                resource_type=resource_type,
                internal_id=internal_id,
            )
            .one_or_none()
        )
        return row.external_id if row else None

    def internal_id(
        self, provider: str, resource_type: str, external_id: str
    ) -> UUID:
        row = (
            self._s.query(ExternalIdentityRow)
            .filter_by(
                provider=provider,
                resource_type=resource_type,
                external_id=str(external_id),
            )
            .one_or_none()
        )
        if row:
            return row.internal_id
        internal_id = uuid4()
        self.bind(provider, resource_type, str(external_id), internal_id)
        return internal_id

    def bind(
        self,
        provider: str,
        resource_type: str,
        external_id: str,
        internal_id: UUID,
    ) -> None:
        row = (
            self._s.query(ExternalIdentityRow)
            .filter_by(
                provider=provider,
                resource_type=resource_type,
                external_id=str(external_id),
            )
            .one_or_none()
        )
        if row is None:
            self._s.add(
                ExternalIdentityRow(
                    provider=provider,
                    resource_type=resource_type,
                    external_id=str(external_id),
                    internal_id=internal_id,
                )
            )
        else:
            row.internal_id = internal_id
        self._s.flush()

    def delete(self, provider: str, resource_type: str, internal_id: UUID) -> None:
        (
            self._s.query(ExternalIdentityRow)
            .filter_by(
                provider=provider,
                resource_type=resource_type,
                internal_id=internal_id,
            )
            .delete(synchronize_session="fetch")
        )
