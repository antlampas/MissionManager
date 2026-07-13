# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from ...domain.acl import Operation, ResourceRef
from ...domain.enums import AssigneeType, ResourceType, Status
from ...domain.events import (
    ActivityAssigned,
    ActivityStatusChanged,
    AssignmentStatusChanged,
    EventPublisherPort,
)
from ...domain.exceptions import NotFoundError, ValidationError
from ...domain.plugins import HookContext, HookPoint
from ...domain.repositories import (
    ActivityRepository,
    GroupRepository,
    MissionAssignmentRepository,
    ObjectiveRepository,
    PersonRepository,
)
from .dto import ActivityDTO
from ._shared import (
    ACTIVITY_ASSIGNMENT_POLICY,
    ASSIGNMENT_STATUS_POLICY,
    require_operator_id,
    transactional,
)
from ..plugin_registry import PluginRegistry


class ActivityService:
    """Gestisce il ciclo di vita delle Activity.

    Non espone create() pubblicamente: le attività nascono dentro
    AssignmentService.create() durante la replicazione del blueprint.
    L'enforcement primario resta al confine; il service ricontrolla le ACL
    quando riceve un operatore o un contesto frontend/CLI.
    """

    def __init__(
        self,
        activity_repo: ActivityRepository,
        objective_repo: ObjectiveRepository,
        assignment_repo: MissionAssignmentRepository,
        person_repo: PersonRepository,
        group_repo: GroupRepository,
        authorization_policy=None,
        plugin_registry: Optional[PluginRegistry] = None,
        event_publisher: Optional[EventPublisherPort] = None,
        uow=None,
    ) -> None:
        self._activity_repo = activity_repo
        self._objective_repo = objective_repo
        self._assignment_repo = assignment_repo
        self._person_repo = person_repo
        self._group_repo = group_repo
        self._authz = authorization_policy
        self._plugin_registry = plugin_registry
        self._events = event_publisher
        self._uow = uow

    @transactional
    def get(self, id: str, operator_id: Optional[UUID] = None) -> ActivityDTO:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.VIEW,
            ResourceRef(ResourceType.ACTIVITY, UUID(id)),
        )
        activity = self._activity_repo.get(UUID(id))
        return ActivityDTO.from_activity(activity)

    @transactional
    def assign_to(
        self,
        activity_id: str,
        person_id: str,
        operator_id: Optional[UUID] = None,
    ) -> ActivityDTO:
        op_id = require_operator_id(operator_id)
        activity_uuid = UUID(activity_id)
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.ASSIGN,
            ResourceRef(ResourceType.ACTIVITY, activity_uuid),
        )
        person_uuid = UUID(person_id)

        if not self._person_repo.exists(person_uuid):
            raise NotFoundError(
                f"Person {person_id} non trovata",
                resource_type="person",
                resource_id=person_uuid,
            )

        activity = self._activity_repo.get(activity_uuid)
        objective = self._objective_repo.get(activity.objective_id)
        if objective.assignment_id is None:
            raise ValidationError(
                "Non è possibile assegnare un'attività appartenente al blueprint della missione"
            )
        assignment = self._assignment_repo.get(objective.assignment_id)

        if assignment.assignee_type == AssigneeType.GROUP:
            members = [p.id for p in self._person_repo.get_by_group(assignment.assignee_id)]
        else:
            members = []
        ACTIVITY_ASSIGNMENT_POLICY.validate_person_in_assignment(
            person_uuid,
            assignment.assignee_type,
            assignment.assignee_id,
            members,
        )

        if person_uuid in activity.assignees:
            raise ValidationError(
                "La persona è già assegnata a questa attività",
                field="person_id",
            )

        activity.assignees.append(person_uuid)
        if activity.status == Status.UNASSIGNED:
            activity.update_status(Status.ASSIGNED)
        self._activity_repo.save(activity)

        if self._events:
            self._events.publish(ActivityAssigned(
                occurred_at=datetime.now(tz=timezone.utc),
                activity_id=activity_uuid,
                person_id=person_uuid,
                operator_id=op_id,
            ))

        return ActivityDTO.from_activity(activity)

    @transactional
    def unassign(
        self,
        activity_id: str,
        person_id: str,
        operator_id: Optional[UUID] = None,
    ) -> ActivityDTO:
        op_id = require_operator_id(operator_id)
        activity_uuid = UUID(activity_id)
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.ASSIGN,
            ResourceRef(ResourceType.ACTIVITY, activity_uuid),
        )
        activity = self._activity_repo.get(activity_uuid)
        person_uuid = UUID(person_id)
        ASSIGNMENT_STATUS_POLICY.validate_activity_unassign(activity.status)
        if person_uuid not in activity.assignees:
            raise ValidationError(
                "La persona non è assegnata a questa attività",
                field="person_id",
            )
        activity.assignees.remove(person_uuid)
        if not activity.assignees and activity.status == Status.ASSIGNED:
            activity.update_status(Status.UNASSIGNED)
        self._activity_repo.save(activity)
        return ActivityDTO.from_activity(activity)

    @transactional
    def update_status(
        self,
        activity_id: str,
        status: str,
        operator_id: Optional[UUID] = None,
    ) -> ActivityDTO:
        activity_uuid = UUID(activity_id)
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.UPDATE_STATUS,
            ResourceRef(ResourceType.ACTIVITY, activity_uuid),
        )
        activity = self._activity_repo.get(activity_uuid)
        new_status = Status(status)

        # Fetch anticipato: serve per il guard blueprint, per il cascade e per gli eventi.
        objective = self._objective_repo.get(activity.objective_id)
        if objective.assignment_id is None:
            raise ValidationError(
                "Non è possibile aggiornare lo stato di un'attività del blueprint della missione"
            )

        ASSIGNMENT_STATUS_POLICY.validate_transition(activity.status, new_status)
        ASSIGNMENT_STATUS_POLICY.validate_activity_in_progress(
            new_status, activity.assignees
        )

        _op_id = require_operator_id(operator_id)
        old_status = activity.status
        if self._plugin_registry:
            ctx = HookContext(
                hook_point=HookPoint.BEFORE_UPDATE_STATUS,
                operator_id=_op_id,
                payload={
                    "entity_id": activity_id,
                    "entity_type": "ACTIVITY",
                    "new_status": status,
                },
            )
            self._plugin_registry.fire(HookPoint.BEFORE_UPDATE_STATUS, ctx)

        activity.update_status(new_status)
        self._activity_repo.save(activity)

        # Auto-cascade: l'attività avvia o fallisce anche l'assignment padre.
        assignment = self._assignment_repo.get(objective.assignment_id)
        if new_status == Status.IN_PROGRESS and assignment.status == Status.ASSIGNED:
            old_assignment_status = assignment.status
            assignment.update_status(Status.IN_PROGRESS)
            self._assignment_repo.save(assignment)
            if self._events:
                self._events.publish(AssignmentStatusChanged(
                    occurred_at=datetime.now(tz=timezone.utc),
                    assignment_id=assignment.id,
                    operator_id=_op_id,
                    old_status=old_assignment_status,
                    new_status=assignment.status,
                ))
        elif new_status == Status.FAILED and not assignment.status.is_terminal():
            old_assignment_status = assignment.status
            assignment.update_status(Status.FAILED)
            self._assignment_repo.save(assignment)
            if self._events:
                self._events.publish(AssignmentStatusChanged(
                    occurred_at=datetime.now(tz=timezone.utc),
                    assignment_id=assignment.id,
                    operator_id=_op_id,
                    old_status=old_assignment_status,
                    new_status=assignment.status,
                ))

        if self._plugin_registry:
            ctx_after = HookContext(
                hook_point=HookPoint.AFTER_UPDATE_STATUS,
                operator_id=_op_id,
                payload=ctx.payload,
                result=activity,
            )
            self._plugin_registry.fire(HookPoint.AFTER_UPDATE_STATUS, ctx_after)

        if self._events:
            self._events.publish(ActivityStatusChanged(
                occurred_at=datetime.now(tz=timezone.utc),
                activity_id=UUID(activity_id),
                assignment_id=objective.assignment_id,
                operator_id=_op_id,
                old_status=old_status,
                new_status=new_status,
            ))

        return ActivityDTO.from_activity(activity)

    @transactional
    def list_by_objective(
        self, objective_id: str, operator_id: Optional[UUID] = None
    ) -> list[ActivityDTO]:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.LIST,
            ResourceRef(ResourceType.OBJECTIVE, UUID(objective_id)),
        )
        activities = self._activity_repo.get_by_objective(UUID(objective_id))
        return [ActivityDTO.from_activity(a) for a in activities]
