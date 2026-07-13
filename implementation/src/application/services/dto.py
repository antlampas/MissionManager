# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ...domain.entities import (
        Activity,
        Badge,
        BadgeAward,
        Group,
        Mission,
        MissionAssignment,
        Objective,
        Person,
    )


@dataclass
class BadgeDTO:
    id: str
    name: str
    description: str
    image_url: Optional[str]

    @classmethod
    def from_badge(cls, badge: Badge) -> BadgeDTO:
        return cls(
            id=str(badge.id),
            name=badge.name,
            description=badge.description,
            image_url=badge.image_url,
        )


@dataclass
class BadgeAwardDTO:
    id: str
    badge: BadgeDTO
    target_type: str
    target_id: str
    recipients: list[str]
    recipients_count: int
    awarded_at: str

    @classmethod
    def from_award(
        cls,
        award: BadgeAward,
        badge: Optional[Badge] = None,
    ) -> BadgeAwardDTO:
        badge_dto = (
            BadgeDTO.from_badge(badge)
            if badge is not None
            else BadgeDTO(id=str(award.badge_id), name="", description="", image_url=None)
        )
        return cls(
            id=str(award.id),
            badge=badge_dto,
            target_type=award.target_type,
            target_id=str(award.target_id),
            recipients=[str(r) for r in award.recipients],
            recipients_count=len(award.recipients),
            awarded_at=award.awarded_at.isoformat(),
        )


@dataclass
class ActivityDTO:
    id: str
    title: str
    description: str
    status: str
    assignees: list[str]
    badge_award: Optional[BadgeAwardDTO]

    @classmethod
    def from_activity(cls, activity: Activity) -> ActivityDTO:
        award_dto = (
            BadgeAwardDTO.from_award(activity.badge_award)
            if activity.badge_award is not None
            else None
        )
        return cls(
            id=str(activity.id),
            title=activity.title,
            description=activity.description,
            status=activity.status.value,
            assignees=[str(a) for a in activity.assignees],
            badge_award=award_dto,
        )


@dataclass
class ObjectiveDTO:
    id: str
    description: str
    outcome: Optional[str]
    activities: list[ActivityDTO]

    @classmethod
    def from_objective(cls, objective: Objective) -> ObjectiveDTO:
        return cls(
            id=str(objective.id),
            description=objective.description,
            outcome=objective.compute_outcome(),
            activities=[ActivityDTO.from_activity(a) for a in objective.activities],
        )


@dataclass
class MissionDTO:
    id: str
    title: str
    description: str
    assignment_policy: dict
    objectives: list[ObjectiveDTO]

    @classmethod
    def from_mission(cls, mission: Mission) -> MissionDTO:
        policy = mission.assignment_policy
        if policy.max_total is None and policy.max_concurrent is None:
            policy_dict: dict = {"unlimited": True}
        else:
            policy_dict = {}
            if policy.max_total is not None:
                policy_dict["max_total"] = policy.max_total
            if policy.max_concurrent is not None:
                policy_dict["max_concurrent"] = policy.max_concurrent
        return cls(
            id=str(mission.id),
            title=mission.title,
            description=mission.description,
            assignment_policy=policy_dict,
            objectives=[ObjectiveDTO.from_objective(obj) for obj in mission.objectives],
        )


@dataclass
class AssignmentDTO:
    id: str
    mission_id: str
    status: str
    objectives: list[ObjectiveDTO]
    assignee_type: Optional[str] = None
    assignee_id: Optional[str] = None
    outcome: Optional[str] = None
    badge_award: Optional[BadgeAwardDTO] = None

    @classmethod
    def from_assignment(cls, assignment: MissionAssignment) -> AssignmentDTO:
        award_dto = (
            BadgeAwardDTO.from_award(assignment.badge_award)
            if assignment.badge_award is not None
            else None
        )
        return cls(
            id=str(assignment.id),
            mission_id=str(assignment.mission_id),
            status=assignment.status.value,
            objectives=[ObjectiveDTO.from_objective(obj) for obj in assignment.objectives],
            assignee_type=assignment.assignee_type.value if assignment.assignee_type else None,
            assignee_id=str(assignment.assignee_id) if assignment.assignee_id else None,
            outcome=assignment.compute_outcome(),
            badge_award=award_dto,
        )


@dataclass
class PersonDTO:
    id: str
    nicknames: list[str]
    primary_nickname: str
    acl_level: int
    acl_groups: list[str]

    @classmethod
    def from_person(cls, person: Person) -> PersonDTO:
        return cls(
            id=str(person.id),
            nicknames=list(person.nicknames),
            primary_nickname=person.primary_nickname(),
            acl_level=person.acl.level,
            acl_groups=person.acl.stored_groups(),
        )


@dataclass
class AclEntryDTO:
    """Vista di trasferimento di una AclEntry (DESIGN §10)."""

    id: str
    subject_type: str
    subject_id: Optional[str]
    resource_type: str
    resource_id: str
    operation: str
    permission: str
    level: Optional[int]
    group: Optional[str]
    profile_join: str
    subject_join: str

    @classmethod
    def from_entry(cls, entry) -> "AclEntryDTO":
        resource_type = getattr(entry.resource.type, "value", entry.resource.type)
        resource_id = entry.resource.key() if hasattr(entry.resource, "key") else entry.resource.id
        operation = getattr(entry.operation, "value", entry.operation)
        return cls(
            id=str(entry.id),
            subject_type=entry.subject.type.value,
            subject_id=entry.subject.id,
            resource_type=str(resource_type),
            resource_id=str(resource_id),
            operation=str(operation),
            permission=entry.permission.value,
            level=entry.level,
            group=entry.group,
            profile_join=entry.profile_join.value,
            subject_join=entry.subject_join.value,
        )


@dataclass
class GroupDTO:
    id: str
    name: Optional[str] = None
    zone_type: Optional[str] = None
    zone_description: Optional[str] = None

    @classmethod
    def from_group(cls, group: Group) -> GroupDTO:
        # Il "nome" e i dati di zona di un gruppo risiedono nella Zone opzionale.
        zone = group.zone
        return cls(
            id=str(group.id),
            name=zone.name if zone else None,
            zone_type=zone.type.value if zone else None,
            zone_description=zone.description if zone else None,
        )
