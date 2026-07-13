# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

from .acl import Profile
from .enums import AssigneeType, Status, ZoneType
from .exceptions import StatusTransitionError, ValidationError
from .value_objects import AssignmentPolicy


@dataclass
class Zone:
    id: UUID
    type: ZoneType
    name: str
    description: Optional[str] = None

    def validate(self) -> None:
        if not self.name:
            raise ValidationError("Zone richiede un nome", field="name")


@dataclass
class Group:
    id: UUID
    zone: Optional[Zone] = None

    def validate(self) -> None:
        # Un gruppo può esistere senza una zona associata.
        return None


@dataclass
class Person:
    id: UUID
    nicknames: list[str]
    # Profilo di autorizzazione valutato dal sistema ACL (DESIGN §10): livello
    # (più basso = più privilegiato) e gruppi ACL. L'entità lo trasporta ma non
    # esegue mai controlli: l'enforcement avviene al confine del sistema.
    acl: Profile = field(default_factory=Profile)

    def primary_nickname(self) -> str:
        return self.nicknames[0] if self.nicknames else ""

    def validate(self) -> None:
        if not self.nicknames or not any(n.strip() for n in self.nicknames):
            raise ValidationError("Person richiede almeno un nickname non vuoto", field="nicknames")


@dataclass
class Badge:
    id: UUID
    name: str
    description: str
    image_url: Optional[str] = None


@dataclass
class BadgeAward:
    id: UUID
    badge_id: UUID
    target_type: str
    target_id: UUID
    recipients: list[UUID]
    awarded_at: datetime


@dataclass
class Activity:
    id: UUID
    title: str
    description: str
    status: Status
    objective_id: UUID
    assignees: list[UUID] = field(default_factory=list)
    badge_award: Optional[BadgeAward] = None

    def update_status(self, new_status: Status) -> None:
        if not self.status.can_transition_to(new_status):
            raise StatusTransitionError(
                f"Transizione non consentita: {self.status.value} → {new_status.value}",
                current_status=self.status.value,
                requested_status=new_status.value,
            )
        self.status = new_status

    def validate(self) -> None:
        if not self.title or not self.title.strip():
            raise ValidationError("Activity richiede un titolo", field="title")


@dataclass
class Objective:
    id: UUID
    description: str
    activities: list[Activity] = field(default_factory=list)
    assignment_id: Optional[UUID] = None
    mission_id: Optional[UUID] = None

    def compute_outcome(self) -> Optional[str]:
        if not self.activities:
            return None
        statuses = [a.status for a in self.activities]
        if all(s == Status.COMPLETED for s in statuses):
            return "COMPLETED"
        if any(s == Status.FAILED for s in statuses):
            return "FAILED"
        if any(s == Status.IN_PROGRESS for s in statuses):
            return "IN_PROGRESS"
        return None

    def validate(self) -> None:
        if not self.activities:
            raise ValidationError("Un obiettivo deve avere almeno un'attività", field="activities")
        for activity in self.activities:
            if activity.objective_id != self.id:
                raise ValidationError(
                    "Ogni attività deve appartenere all'obiettivo corrente",
                    field="activities",
                )
            activity.validate()


@dataclass
class MissionAssignment:
    id: UUID
    mission_id: UUID
    status: Status
    objectives: list[Objective] = field(default_factory=list)
    assignee_type: Optional[AssigneeType] = None
    assignee_id: Optional[UUID] = None
    badge_award: Optional[BadgeAward] = None

    def assign_to(self, assignee_type: AssigneeType, assignee_id: UUID) -> None:
        self.assignee_type = assignee_type
        self.assignee_id = assignee_id
        if self.status == Status.UNASSIGNED:
            self.update_status(Status.ASSIGNED)

    def update_status(self, new_status: Status) -> None:
        if not self.status.can_transition_to(new_status):
            raise StatusTransitionError(
                f"Transizione non consentita: {self.status.value} → {new_status.value}",
                current_status=self.status.value,
                requested_status=new_status.value,
            )
        self.status = new_status

    def award_badge(self, award: BadgeAward) -> None:
        if self.status != Status.COMPLETED:
            raise ValidationError(
                "Il badge può essere assegnato solo a un assignment COMPLETED"
            )
        self.badge_award = award

    def is_completed(self) -> bool:
        return self.status == Status.COMPLETED

    def compute_outcome(self) -> Optional[str]:
        if not self.objectives:
            return None
        outcomes = [obj.compute_outcome() for obj in self.objectives]
        if all(o == "COMPLETED" for o in outcomes):
            return "COMPLETED"
        if any(o == "FAILED" for o in outcomes):
            return "FAILED"
        if any(o == "IN_PROGRESS" for o in outcomes):
            return "IN_PROGRESS"
        return None

    def validate(self) -> None:
        has_type = self.assignee_type is not None
        has_id = self.assignee_id is not None
        if has_type != has_id:
            raise ValidationError(
                "assignee_type e assignee_id devono essere valorizzati insieme",
                field="assignee_id",
            )
        if self.status == Status.UNASSIGNED and (has_type or has_id):
            raise ValidationError(
                "Un assignment UNASSIGNED non può avere un assegnatario",
                field="status",
            )
        if self.status != Status.UNASSIGNED and not (has_type and has_id):
            raise ValidationError(
                "Un assignment assegnato deve avere tipo e ID dell'assegnatario",
                field="assignee_id",
            )
        if not self.objectives:
            raise ValidationError(
                "Un assignment deve contenere almeno un obiettivo",
                field="objectives",
            )
        for objective in self.objectives:
            if objective.assignment_id != self.id:
                raise ValidationError(
                    "Ogni obiettivo deve appartenere all'assignment corrente",
                    field="objectives",
                )
            objective.validate()


@dataclass
class Mission:
    id: UUID
    title: str
    description: str
    assignment_policy: AssignmentPolicy
    objectives: list[Objective] = field(default_factory=list)

    def validate(self) -> None:
        if not self.title:
            raise ValidationError("title è obbligatorio", field="title")
        if not self.objectives:
            raise ValidationError(
                "Una missione deve avere almeno un obiettivo", field="objectives"
            )
        for obj in self.objectives:
            obj.validate()

    # Nota: il blueprint è immutabile dopo la creazione — obiettivi e attività si
    # definiscono solo in fase di costruzione (MissionService.create). Non esiste
    # alcun metodo per aggiungere o modificare obiettivi/attività a posteriori.
