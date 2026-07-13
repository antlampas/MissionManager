# SPDX-License-Identifier: CC-BY-SA-4.0
"""In-memory rate limiting per operazioni MissionManager.

Un'istanza per processo; i timestamp scadono ogni window_seconds.
Thread-safe via threading.Lock.  Non adatto a deployment multi-processo
(usare Redis o uno store condiviso in quel caso).
"""
from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from uuid import UUID

from ...shared.errors import RateLimitExceededError

logger = logging.getLogger(__name__)

# GC: dopo quante chiamate a check() pulire i contatori scaduti.
_GC_INTERVAL = 1000


class RateLimitedOperation(str, Enum):
    CREATE_MISSION = "CREATE_MISSION"
    DELETE_MISSION = "DELETE_MISSION"
    CREATE_ASSIGNMENT = "CREATE_ASSIGNMENT"
    ASSIGN_ASSIGNMENT = "ASSIGN_ASSIGNMENT"
    UPDATE_ASSIGNMENT_STATUS = "UPDATE_ASSIGNMENT_STATUS"
    UPDATE_ACTIVITY_STATUS = "UPDATE_ACTIVITY_STATUS"
    ASSIGN_ACTIVITY = "ASSIGN_ACTIVITY"
    UNASSIGN_ACTIVITY = "UNASSIGN_ACTIVITY"
    CREATE_BADGE = "CREATE_BADGE"
    AWARD_BADGE = "AWARD_BADGE"
    ADD_PERSON = "ADD_PERSON"
    UPDATE_PERSON = "UPDATE_PERSON"
    REMOVE_PERSON = "REMOVE_PERSON"
    CREATE_GROUP = "CREATE_GROUP"
    UPDATE_GROUP = "UPDATE_GROUP"
    REMOVE_GROUP = "REMOVE_GROUP"
    ADD_GROUP_MEMBER = "ADD_GROUP_MEMBER"
    REMOVE_GROUP_MEMBER = "REMOVE_GROUP_MEMBER"
    CHANGE_PASSWORD = "CHANGE_PASSWORD"
    OTHER_MUTATION = "OTHER_MUTATION"


_DEFAULT_LIMITS: dict[RateLimitedOperation, int] = {
    RateLimitedOperation.CREATE_MISSION: 20,
    RateLimitedOperation.DELETE_MISSION: 10,
    RateLimitedOperation.CREATE_ASSIGNMENT: 50,
    RateLimitedOperation.ASSIGN_ASSIGNMENT: 50,
    RateLimitedOperation.UPDATE_ASSIGNMENT_STATUS: 100,
    RateLimitedOperation.UPDATE_ACTIVITY_STATUS: 200,
    RateLimitedOperation.ASSIGN_ACTIVITY: 100,
    RateLimitedOperation.UNASSIGN_ACTIVITY: 100,
    RateLimitedOperation.CREATE_BADGE: 20,
    RateLimitedOperation.AWARD_BADGE: 20,
    RateLimitedOperation.ADD_PERSON: 30,
    RateLimitedOperation.UPDATE_PERSON: 60,
    RateLimitedOperation.REMOVE_PERSON: 10,
    RateLimitedOperation.CREATE_GROUP: 30,
    RateLimitedOperation.UPDATE_GROUP: 60,
    RateLimitedOperation.REMOVE_GROUP: 10,
    RateLimitedOperation.ADD_GROUP_MEMBER: 60,
    RateLimitedOperation.REMOVE_GROUP_MEMBER: 60,
    RateLimitedOperation.CHANGE_PASSWORD: 20,
    RateLimitedOperation.OTHER_MUTATION: 60,
}

_DEFAULT_WINDOW_SECONDS = 60


class InMemoryRateLimitPolicy:
    """Rate limiter per (operatore, operazione) con finestra scorrevole.

    I timestamp sono accumulati per chiave (operator_id, operation); ad ogni
    check() vengono espulsi quelli più vecchi di window_seconds.  Un GC
    periodico rimuove le chiavi inattive per evitare leak di memoria.
    """

    def __init__(
        self,
        limits: dict[RateLimitedOperation, int] | None = None,
        window_seconds: int = _DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self._limits = limits or _DEFAULT_LIMITS
        self._window = window_seconds
        self._counters: dict[tuple, list[float]] = {}
        self._lock = threading.Lock()
        self._calls_since_gc: int = 0

    def check(self, operator_id: UUID, operation: RateLimitedOperation) -> None:
        """Solleva RateLimitExceededError se la quota è stata superata."""
        limit = self._limits.get(operation)
        if limit is None:
            return

        key = (operator_id, operation)
        now = time.monotonic()
        cutoff = now - self._window

        with self._lock:
            self._calls_since_gc += 1
            if self._calls_since_gc >= _GC_INTERVAL:
                self._gc(now)
                self._calls_since_gc = 0

            timestamps = self._counters.setdefault(key, [])
            timestamps[:] = [t for t in timestamps if t >= cutoff]
            if len(timestamps) >= limit:
                logger.warning(
                    "rate_limit operator=%s operation=%s count=%d limit=%d",
                    operator_id, operation.value, len(timestamps), limit,
                )
                raise RateLimitExceededError(
                    f"Rate limit superato per {operation.value}: "
                    f"max {limit} richieste per {self._window}s",
                    operation=operation.value,
                    limit=limit,
                    window=self._window,
                )
            timestamps.append(now)

    def _gc(self, now: float) -> None:
        cutoff = now - self._window
        stale = [k for k, ts in self._counters.items() if not ts or ts[-1] < cutoff]
        for k in stale:
            del self._counters[k]


class NoOpRateLimitPolicy:
    """Rate limit policy che non applica alcuna limitazione.

    Usato dalla CLI locale e nei test dove il rate limiting non è necessario.
    """

    def check(self, operator_id: UUID, operation: RateLimitedOperation) -> None:
        pass
