# SPDX-License-Identifier: CC-BY-SA-4.0
"""Clock implementations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass
class FrozenClock:
    value: datetime

    def now(self) -> datetime:
        return self.value

    def set(self, value: datetime) -> None:
        self.value = value
