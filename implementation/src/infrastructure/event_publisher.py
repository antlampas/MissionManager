# SPDX-License-Identifier: CC-BY-SA-4.0
"""Transactional outbox per gli eventi di dominio.

``publish`` non esegue side effect: scrive l'evento nella stessa transazione
del caso d'uso. I consumer lo leggono solo dopo il commit, con una consegna
idempotente per consumer; REST, Web e CLI possono quindi essere processi
separati senza perdere eventi.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
from uuid import UUID, uuid4

from ..domain.events import DomainEvent
from .repositories.models import OutboxDeliveryRow, OutboxEventRow
from .repositories.session import SqlAlchemySessionProvider, SqlAlchemyUnitOfWork

logger = logging.getLogger(__name__)

OutboxHandler = Callable[[str, dict[str, Any]], None]


def _json_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return value


class EventPublisher:
    def __init__(self, sessions: SqlAlchemySessionProvider, uow: SqlAlchemyUnitOfWork) -> None:
        self._sessions = sessions
        self._uow = uow
        self._consumers: dict[str, OutboxHandler] = {}

    def register_consumer(self, name: str, handler: OutboxHandler) -> None:
        if name in self._consumers:
            raise ValueError(f"Consumer eventi già registrato: {name}")
        self._consumers[name] = handler

    def replace_consumer(self, name: str, handler: OutboxHandler) -> None:
        self._consumers[name] = handler

    def publish(self, event: DomainEvent) -> None:
        """Accoda l'evento alla transazione attiva senza eseguire side effect."""
        row = OutboxEventRow(
            id=uuid4(),
            event_type=type(event).__name__,
            payload=_json_value(event),
            occurred_at=event.occurred_at,
        )
        self._sessions.add(row)

    def dispatch_consumer(self, name: str, limit: int = 100) -> int:
        handler = self._consumers.get(name)
        if handler is None:
            return 0

        delivered = 0
        with self._uow.transaction():
            session = self._sessions.current_session()
            rows = (
                session.query(OutboxEventRow)
                .outerjoin(
                    OutboxDeliveryRow,
                    (OutboxDeliveryRow.event_id == OutboxEventRow.id)
                    & (OutboxDeliveryRow.consumer == name),
                )
                .filter(OutboxDeliveryRow.id.is_(None))
                .order_by(OutboxEventRow.occurred_at, OutboxEventRow.id)
                .limit(limit)
                # ``of=`` limita il lock alla tabella eventi: PostgreSQL rifiuta
                # FOR UPDATE sul lato nullable di un outer join.
                .with_for_update(skip_locked=True, of=OutboxEventRow)
                .all()
            )
            for row in rows:
                try:
                    handler(row.event_type, dict(row.payload))
                    session.add(OutboxDeliveryRow(event_id=row.id, consumer=name))
                    delivered += 1
                except Exception:
                    logger.exception(
                        "Consumer outbox '%s' fallito per evento %s", name, row.id
                    )
        return delivered

    def dispatch_registered(self) -> int:
        return sum(self.dispatch_consumer(name) for name in self._consumers)
