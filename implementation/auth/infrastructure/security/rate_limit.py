# SPDX-License-Identifier: CC-BY-SA-4.0
"""Rate-limit adapters."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from auth.domain.request import AuthRequest
from auth.ports.security import RateLimitResult


class NoopRateLimitPolicy:
    def check(self, request: AuthRequest) -> RateLimitResult:
        return RateLimitResult(True)


class InMemoryRateLimitPolicy:
    def __init__(self, *, max_requests: int = 60, window: timedelta = timedelta(minutes=1)) -> None:
        self._max_requests = max_requests
        self._window = window
        self._hits: dict[str, deque[datetime]] = defaultdict(deque)

    def check(self, request: AuthRequest) -> RateLimitResult:
        key = self._key(request)
        now = datetime.now(timezone.utc)
        bucket = self._hits[key]
        while bucket and bucket[0] <= now - self._window:
            bucket.popleft()
        if len(bucket) >= self._max_requests:
            retry = int((bucket[0] + self._window - now).total_seconds()) + 1
            return RateLimitResult(False, retry_after_seconds=retry)
        bucket.append(now)
        return RateLimitResult(True)

    def _key(self, request: AuthRequest) -> str:
        return "|".join((request.origin.name, request.origin.address or "-", request.operation or "-"))
