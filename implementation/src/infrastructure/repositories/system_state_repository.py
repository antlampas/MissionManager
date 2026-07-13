# SPDX-License-Identifier: CC-BY-SA-4.0
"""Guardie atomiche persistenti per le operazioni di bootstrap."""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from ...domain.exceptions import ValidationError
from .models import SystemStateRow


class SqlAlchemySystemStateRepository:
    _INITIAL_ADMIN_KEY = "initial_admin_claimed"

    def __init__(self, session) -> None:
        self._s = session

    def claim_initial_admin(self) -> str:
        """Rivendica il bootstrap una sola volta nella transazione corrente.

        Il vincolo PK rende atomico il controllo anche con più richieste o
        processi concorrenti. Un rollback (ad esempio password non valida)
        libera automaticamente la rivendicazione.
        """
        try:
            claim_id = str(uuid4())
            with self._s.begin_nested():
                self._s.add(SystemStateRow(key=self._INITIAL_ADMIN_KEY, value=claim_id))
                self._s.flush()
            return claim_id
        except IntegrityError:
            raise ValidationError(
                "Il bootstrap iniziale è già in corso o è già stato completato"
            ) from None

    def release_initial_admin(self, claim_id: str) -> None:
        """Rilascia soltanto il claim creato da questo tentativo OIDC fallito."""
        self._s.execute(
            delete(SystemStateRow).where(
                SystemStateRow.key == self._INITIAL_ADMIN_KEY,
                SystemStateRow.value == claim_id,
            )
        )
