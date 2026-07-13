# SPDX-License-Identifier: CC-BY-SA-4.0
"""SqlAlchemyCredentialRepository — credenziali locali (hash bcrypt + lockout)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ...domain.auth import LocalCredential
from .models import CredentialRow


class SqlAlchemyCredentialRepository:

    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, person_id: UUID) -> Optional[LocalCredential]:
        row = self._s.get(CredentialRow, person_id)
        if row is None:
            return None
        return LocalCredential(
            person_id=row.person_id,
            hashed_password=row.hashed_password,
            failed_attempts=row.failed_attempts or 0,
            locked_until=row.locked_until,
            must_change_password=bool(row.must_change_password),
        )

    def save(self, credential: LocalCredential) -> None:
        now = datetime.now(timezone.utc)
        row = self._s.get(CredentialRow, credential.person_id)
        if row is None:
            self._s.add(
                CredentialRow(
                    person_id=credential.person_id,
                    hashed_password=credential.hashed_password,
                    failed_attempts=credential.failed_attempts,
                    locked_until=credential.locked_until,
                    must_change_password=credential.must_change_password,
                )
            )
        else:
            # ``changed_at`` traccia il cambio *password*: si aggiorna solo se
            # l'hash muta, non sui salvataggi di solo stato lockout.
            if row.hashed_password != credential.hashed_password:
                row.changed_at = now
            row.hashed_password = credential.hashed_password
            row.failed_attempts = credential.failed_attempts
            row.locked_until = credential.locked_until
            row.must_change_password = credential.must_change_password
        self._s.flush()

    def delete(self, person_id: UUID) -> bool:
        row = self._s.get(CredentialRow, person_id)
        if not row:
            return False
        self._s.delete(row)
        self._s.flush()
        return True
