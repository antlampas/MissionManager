# SPDX-License-Identifier: CC-BY-SA-4.0
"""Audit ports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Protocol


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    occurred_at: datetime
    subject: str | None = None
    outcome: str | None = None
    correlation_id: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)


class AuditLogger(Protocol):
    def record(self, event_type: str, **fields: object) -> None: ...


class AuditLogRepository(Protocol):
    def append(self, event: AuditEvent) -> None: ...

    def list_events(self) -> list[AuditEvent]: ...
