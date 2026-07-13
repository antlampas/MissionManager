# SPDX-License-Identifier: CC-BY-SA-4.0
"""Audit logger strutturato per le operazioni MissionManager.

Ogni cambio di stato significativo viene emesso sul logger "missionmanager.audit"
in modo che un aggregatore centralizzato (ELK, Loki, …) possa raccoglierlo.

Formato (una riga per evento):
  AUDIT operator=<uuid> action=<ACTION> resource=<type>:<id> outcome=<...> [detail=<str>]
"""
from __future__ import annotations

import logging
from enum import Enum
from uuid import UUID

logger = logging.getLogger("missionmanager.audit")


class AuditOutcome(str, Enum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    ERROR = "ERROR"


class AuditAction(str, Enum):
    CREATE_MISSION = "CREATE_MISSION"
    DELETE_MISSION = "DELETE_MISSION"
    CREATE_ASSIGNMENT = "CREATE_ASSIGNMENT"
    UPDATE_ASSIGNMENT_STATUS = "UPDATE_ASSIGNMENT_STATUS"
    ASSIGN_ACTIVITY = "ASSIGN_ACTIVITY"
    UPDATE_ACTIVITY_STATUS = "UPDATE_ACTIVITY_STATUS"
    AWARD_BADGE = "AWARD_BADGE"
    ADD_PERSON = "ADD_PERSON"
    REMOVE_PERSON = "REMOVE_PERSON"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    SET_PASSWORD = "SET_PASSWORD"
    OIDC_CALLBACK = "OIDC_CALLBACK"


class AuditLogger:
    """Scrive righe di audit strutturate sul logger "missionmanager.audit"."""

    def log(
        self,
        operator_id: UUID | None,
        action: AuditAction,
        resource_type: str,
        resource_id: UUID | str | None,
        outcome: AuditOutcome,
        detail: str | None = None,
    ) -> None:
        operator_str = str(operator_id) if operator_id else "anonymous"
        resource_str = (
            f"{resource_type}:{resource_id}" if resource_id else resource_type
        )
        msg = (
            f"AUDIT operator={operator_str} action={action.value}"
            f" resource={resource_str} outcome={outcome.value}"
        )
        if detail:
            msg += f" detail={detail!r}"
        try:
            logger.info(msg)
        except Exception:
            pass  # l'audit non deve mai crashare il flusso principale

    def handle_outbox_event(self, event_type: str, payload: dict) -> None:
        """Consumer idempotente degli eventi persistiti nell'outbox."""
        action_map = {
            "MissionCreated": AuditAction.CREATE_MISSION,
            "MissionDeleted": AuditAction.DELETE_MISSION,
            "AssignmentCreated": AuditAction.CREATE_ASSIGNMENT,
            "AssignmentStatusChanged": AuditAction.UPDATE_ASSIGNMENT_STATUS,
            "ActivityAssigned": AuditAction.ASSIGN_ACTIVITY,
            "ActivityStatusChanged": AuditAction.UPDATE_ACTIVITY_STATUS,
            "BadgeAwarded": AuditAction.AWARD_BADGE,
        }
        action = action_map.get(event_type)
        if action is None:
            return
        resource_type, resource_id = {
            "MissionCreated": ("mission", payload.get("mission_id")),
            "MissionDeleted": ("mission", payload.get("mission_id")),
            "AssignmentCreated": ("assignment", payload.get("assignment_id")),
            "AssignmentStatusChanged": ("assignment", payload.get("assignment_id")),
            "ActivityAssigned": ("activity", payload.get("activity_id")),
            "ActivityStatusChanged": ("activity", payload.get("activity_id")),
            "BadgeAwarded": ("badge_award", payload.get("badge_award_id")),
        }[event_type]
        operator_raw = payload.get("operator_id")
        try:
            operator_id = UUID(operator_raw) if operator_raw else None
        except ValueError:
            operator_id = None
        self.log(operator_id, action, resource_type, resource_id, AuditOutcome.ALLOWED)


class NoOpAuditLogger:
    """Audit logger che scarta tutti gli eventi.

    Usato dalla CLI locale e nei test dove il logging degli audit non è necessario.
    """

    def log(
        self,
        operator_id: UUID | None,
        action: AuditAction,
        resource_type: str,
        resource_id: UUID | str | None,
        outcome: AuditOutcome,
        detail: str | None = None,
    ) -> None:
        pass

    def handle_outbox_event(self, event_type: str, payload: dict) -> None:
        return None
