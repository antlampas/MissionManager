# SPDX-License-Identifier: CC-BY-SA-4.0
"""Domain events — immutable value objects published after successful persistence.

Consumers (EventPublisher, realtime notifier, audit log) subscribe to these events
and react asynchronously.  Events are never published if the originating operation
failed.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from .enums import AssigneeType, Status


@dataclass(frozen=True)
class DomainEvent:
    """Base for all domain events."""
    occurred_at: datetime


# ── Mission ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MissionCreated(DomainEvent):
    mission_id: UUID
    operator_id: UUID
    title: str


@dataclass(frozen=True)
class MissionDeleted(DomainEvent):
    mission_id: UUID
    operator_id: UUID


# ── MissionAssignment ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AssignmentCreated(DomainEvent):
    assignment_id: UUID
    mission_id: UUID
    operator_id: UUID
    assignee_type: AssigneeType
    assignee_id: UUID


@dataclass(frozen=True)
class AssignmentStatusChanged(DomainEvent):
    assignment_id: UUID
    operator_id: UUID
    old_status: Status
    new_status: Status


# ── Activity ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ActivityAssigned(DomainEvent):
    activity_id: UUID
    person_id: UUID
    operator_id: UUID


@dataclass(frozen=True)
class ActivityStatusChanged(DomainEvent):
    activity_id: UUID
    assignment_id: UUID
    operator_id: UUID
    old_status: Status
    new_status: Status


# ── Badge ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BadgeAwarded(DomainEvent):
    badge_award_id: UUID
    badge_id: UUID
    operator_id: UUID
    target_type: str          # "ASSIGNMENT" | "ACTIVITY"
    target_id: UUID
    recipient_ids: tuple[UUID, ...]


# ── Port ─────────────────────────────────────────────────────────────────────

class EventPublisherPort(Protocol):
    """Porta di dominio per la pubblicazione di domain events.

    I service di application dipendono da questa interfaccia;
    l'implementazione concreta vive in infrastructure.
    """
    def publish(self, event: DomainEvent) -> None: ...
