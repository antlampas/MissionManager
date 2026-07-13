# SPDX-License-Identifier: CC-BY-SA-4.0
"""Adapter Redis opzionali per componenti che devono funzionare tra worker."""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable

from ...shared.errors import RateLimitExceededError
from .rate_limit import RateLimitedOperation, _DEFAULT_LIMITS, _DEFAULT_WINDOW_SECONDS

logger = logging.getLogger(__name__)


def _client(url: str):
    try:
        import redis
    except ImportError as exc:  # pragma: no cover - dipende dall'installazione
        raise RuntimeError(
            "Redis è configurato ma il pacchetto 'redis' non è installato"
        ) from exc
    return redis.Redis.from_url(url, decode_responses=True)


class RedisRateLimitPolicy:
    """Contatore atomico Redis, condiviso da tutti i worker."""

    def __init__(
        self,
        url: str,
        prefix: str,
        limits: dict | None = None,
        window_seconds: int = _DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self._redis = _client(url)
        self._prefix = prefix
        self._limits = limits or _DEFAULT_LIMITS
        self._window = window_seconds

    def check(self, operator_id, operation: RateLimitedOperation) -> None:
        limit = self._limits.get(operation)
        if limit is None:
            return
        key = f"{self._prefix}:rate:{operator_id}:{operation.value}"
        pipeline = self._redis.pipeline()
        pipeline.incr(key)
        pipeline.ttl(key)
        count, ttl = pipeline.execute()
        if ttl < 0:
            self._redis.expire(key, self._window)
        if count > limit:
            raise RateLimitExceededError(
                f"Rate limit superato per {operation.value}: max {limit} richieste per {self._window}s",
                operation=operation.value,
                limit=limit,
                window=self._window,
            )


class RedisTokenRevocationStore:
    def __init__(self, url: str, prefix: str) -> None:
        self._redis = _client(url)
        self._prefix = prefix

    def revoke(self, jti: str, expires_at: datetime) -> None:
        seconds = max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
        self._redis.setex(f"{self._prefix}:revoked-jti:{jti}", seconds, "1")

    def is_revoked(self, jti: str) -> bool:
        return bool(self._redis.exists(f"{self._prefix}:revoked-jti:{jti}"))


class RedisRealtimePublisher:
    """Consumer outbox: pubblica un evento una volta nel canale Redis."""

    def __init__(self, url: str, prefix: str) -> None:
        self._redis = _client(url)
        self._channel = f"{prefix}:realtime"

    def handle_outbox_event(self, event_type: str, payload: dict) -> None:
        if event_type not in {"AssignmentStatusChanged", "ActivityStatusChanged"}:
            return
        self._redis.publish(
            self._channel, json.dumps({"event_type": event_type, "payload": payload})
        )


class RedisRealtimeSubscriber:
    """Riceve pub/sub Redis in un thread e delega al bridge thread-safe Quart."""

    def __init__(self, url: str, prefix: str, callback: Callable[[str, dict], None]) -> None:
        self._redis = _client(url)
        self._channel = f"{prefix}:realtime"
        self._callback = callback
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pubsub = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="mm-redis-realtime")
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._pubsub is not None:
            try:
                self._pubsub.close()
            except Exception:
                logger.debug("Chiusura Redis pubsub fallita", exc_info=True)

    def _run(self) -> None:
        try:
            with self._redis.pubsub(ignore_subscribe_messages=True) as pubsub:
                self._pubsub = pubsub
                pubsub.subscribe(self._channel)
                while not self._stop.is_set():
                    message = pubsub.get_message(timeout=1.0)
                    if not message or message.get("type") != "message":
                        continue
                    data = json.loads(message["data"])
                    self._callback(data["event_type"], data["payload"])
        except Exception:
            if not self._stop.is_set():
                logger.exception("Subscriber realtime Redis interrotto")
