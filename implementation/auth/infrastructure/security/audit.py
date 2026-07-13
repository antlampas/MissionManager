# SPDX-License-Identifier: CC-BY-SA-4.0
"""Audit logger adapter."""

from __future__ import annotations

from datetime import datetime, timezone

from auth.ports.audit import AuditEvent, AuditLogRepository

_SECRET_MARKERS = ("password", "token", "secret", "code", "pkce", "verifier")


class RepositoryAuditLogger:
    def __init__(self, repository: AuditLogRepository) -> None:
        self._repository = repository

    def record(self, event_type: str, **fields: object) -> None:
        safe_fields = {
            key: value
            for key, value in fields.items()
            if not any(marker in key.casefold() for marker in _SECRET_MARKERS)
        }
        subject = safe_fields.pop("subject", None)
        correlation_id = safe_fields.pop("correlation_id", None)
        outcome = safe_fields.pop("outcome", None)
        self._repository.append(
            AuditEvent(
                event_type=event_type,
                occurred_at=datetime.now(timezone.utc),
                subject=str(subject) if subject is not None else None,
                outcome=str(outcome) if outcome is not None else None,
                correlation_id=str(correlation_id) if correlation_id is not None else None,
                details=safe_fields,
            )
        )
