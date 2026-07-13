# SPDX-License-Identifier: CC-BY-SA-4.0
"""Conversion helpers: ORM row ↔ domain entity."""
from __future__ import annotations

from uuid import UUID

from ...domain.entities import (
    Activity,
    Badge,
    BadgeAward,
    Group,
    Mission,
    MissionAssignment,
    Objective,
    Person,
    Zone,
)
from ...domain.acl import Profile
from ...domain.enums import AssigneeType, Status, ZoneType
from ...domain.value_objects import AssignmentPolicy
from .models import (
    ActivityRow,
    AssignmentRow,
    BadgeAwardRow,
    BadgeRow,
    GroupRow,
    MissionRow,
    ObjectiveRow,
    PersonRow,
    ZoneRow,
)


def zone_from_row(row: ZoneRow) -> Zone:
    return Zone(
        id=row.id,
        type=ZoneType(row.type),
        name=row.name,
        description=row.description,
    )


def zone_to_row(entity: Zone, row: ZoneRow | None = None) -> ZoneRow:
    if row is None:
        row = ZoneRow(id=entity.id)
    row.type = entity.type.value
    row.name = entity.name
    row.description = entity.description
    return row


def group_from_row(row: GroupRow) -> Group:
    zone = zone_from_row(row.zone) if row.zone else None
    return Group(id=row.id, zone=zone)


def group_to_row(entity: Group, row: GroupRow | None = None) -> GroupRow:
    if row is None:
        row = GroupRow(id=entity.id)
    row.zone_id = entity.zone.id if entity.zone else None
    return row


def person_from_row(row: PersonRow) -> Person:
    return Person(
        id=row.id,
        nicknames=list(row.nicknames),
        acl=Profile(level=row.acl_level, groups=frozenset(row.acl_groups or [])),
    )


def person_to_row(entity: Person, row: PersonRow | None = None) -> PersonRow:
    if row is None:
        row = PersonRow(id=entity.id)
    row.nicknames = list(entity.nicknames)
    row.acl_level = entity.acl.level
    # Il gruppo universale "public" è implicito: non viene persistito.
    row.acl_groups = entity.acl.stored_groups()
    return row


def badge_from_row(row: BadgeRow) -> Badge:
    return Badge(
        id=row.id,
        name=row.name,
        description=row.description,
        image_url=row.image_url,
    )


def badge_to_row(entity: Badge, row: BadgeRow | None = None) -> BadgeRow:
    if row is None:
        row = BadgeRow(id=entity.id)
    row.name = entity.name
    row.description = entity.description
    row.image_url = entity.image_url
    return row


def badge_award_from_row(row: BadgeAwardRow) -> BadgeAward:
    return BadgeAward(
        id=row.id,
        badge_id=row.badge_id,
        target_type=row.target_type,
        target_id=row.target_id,
        recipients=[UUID(r) for r in row.recipients],
        awarded_at=row.awarded_at,
    )


def badge_award_to_row(entity: BadgeAward, row: BadgeAwardRow | None = None) -> BadgeAwardRow:
    if row is None:
        row = BadgeAwardRow(id=entity.id)
    row.badge_id = entity.badge_id
    row.target_type = entity.target_type
    row.target_id = entity.target_id
    row.recipients = [str(r) for r in entity.recipients]
    row.awarded_at = entity.awarded_at
    return row


def activity_from_row(row: ActivityRow) -> Activity:
    return Activity(
        id=row.id,
        title=row.title,
        description=row.description,
        status=Status(row.status),
        objective_id=row.objective_id,
        assignees=[UUID(a) for a in (row.assignees or [])],
        badge_award=badge_award_from_row(row.badge_award) if row.badge_award else None,
    )


def activity_to_row(entity: Activity, row: ActivityRow | None = None) -> ActivityRow:
    if row is None:
        row = ActivityRow(id=entity.id)
    row.title = entity.title
    row.description = entity.description
    row.status = entity.status.value
    row.objective_id = entity.objective_id
    row.assignees = [str(a) for a in entity.assignees]
    row.badge_award_id = entity.badge_award.id if entity.badge_award else None
    return row


def objective_from_row(row: ObjectiveRow, activities: list[Activity]) -> Objective:
    return Objective(
        id=row.id,
        description=row.description,
        assignment_id=row.assignment_id,
        mission_id=row.mission_id,
        activities=activities,
    )


def objective_to_row(entity: Objective, row: ObjectiveRow | None = None) -> ObjectiveRow:
    if row is None:
        row = ObjectiveRow(id=entity.id)
    row.description = entity.description
    row.mission_id = entity.mission_id
    row.assignment_id = entity.assignment_id
    return row


def mission_from_row(row: MissionRow, objectives: list[Objective]) -> Mission:
    return Mission(
        id=row.id,
        title=row.title,
        description=row.description,
        assignment_policy=AssignmentPolicy(
            max_total=row.policy_max_total,
            max_concurrent=row.policy_max_concurrent,
        ),
        objectives=objectives,
    )


def mission_to_row(entity: Mission, row: MissionRow | None = None) -> MissionRow:
    if row is None:
        row = MissionRow(id=entity.id)
    row.title = entity.title
    row.description = entity.description
    row.policy_max_total = entity.assignment_policy.max_total
    row.policy_max_concurrent = entity.assignment_policy.max_concurrent
    return row


def assignment_from_row(row: AssignmentRow, objectives: list[Objective]) -> MissionAssignment:
    return MissionAssignment(
        id=row.id,
        mission_id=row.mission_id,
        status=Status(row.status),
        objectives=objectives,
        assignee_type=AssigneeType(row.assignee_type) if row.assignee_type else None,
        assignee_id=row.assignee_id,
        badge_award=badge_award_from_row(row.badge_award) if row.badge_award else None,
    )


def assignment_to_row(entity: MissionAssignment, row: AssignmentRow | None = None) -> AssignmentRow:
    if row is None:
        row = AssignmentRow(id=entity.id)
    row.mission_id = entity.mission_id
    row.status = entity.status.value
    row.assignee_type = entity.assignee_type.value if entity.assignee_type else None
    row.assignee_id = entity.assignee_id
    row.badge_award_id = entity.badge_award.id if entity.badge_award else None
    return row
