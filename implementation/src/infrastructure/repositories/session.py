# SPDX-License-Identifier: CC-BY-SA-4.0
"""Sessione SQLAlchemy contestuale e unità di lavoro sincrona.

I repository ricevono questo provider invece di una Session globale. Durante
un caso d'uso mutante l'unità di lavoro crea una Session propria, la rende
disponibile ai repository tramite ContextVar e fa un solo commit alla fine.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator, Optional

from sqlalchemy.orm import Session


class SqlAlchemySessionProvider:
    def __init__(self, session_factory: Callable[[], Session] | Session) -> None:
        self._factory: Optional[Callable[[], Session]] = (
            session_factory if callable(session_factory) else None
        )
        self._direct_session: Optional[Session] = (
            None if callable(session_factory) else session_factory
        )
        self._current: ContextVar[Optional[Session]] = ContextVar(
            "missionmanager_session", default=None
        )

    def current_session(self) -> Session:
        current = self._current.get()
        if current is not None:
            return current
        if self._direct_session is not None:
            return self._direct_session
        raise RuntimeError("Nessuna Session SQLAlchemy attiva per questa operazione")

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        # Le chiamate annidate condividono la transazione del chiamante.
        if self._current.get() is not None:
            yield self.current_session()
            return

        session = self._direct_session or (self._factory() if self._factory else None)
        if session is None:
            raise RuntimeError("Session factory SQLAlchemy non configurata")
        token = self._current.set(session)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            self._current.reset(token)
            if self._direct_session is None:
                session.close()

    def __getattr__(self, name: str):
        """Compatibilità con i repository che usano direttamente self._s."""
        return getattr(self.current_session(), name)


class SqlAlchemyUnitOfWork:
    def __init__(self, sessions: SqlAlchemySessionProvider) -> None:
        self._sessions = sessions

    def transaction(self):
        return self._sessions.transaction()
