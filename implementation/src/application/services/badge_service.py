# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from ...domain.acl import Operation, ResourceRef, SYSTEM_RESOURCE
from ...domain.entities import BadgeAward
from ...domain.enums import AssigneeType, ResourceType, Status
from ...domain.events import BadgeAwarded, EventPublisherPort
from ...domain.exceptions import ValidationError
from ...domain.plugins import HookContext, HookPoint
from ...domain.repositories import (
    ActivityRepository,
    BadgeAwardRepository,
    BadgeRepository,
    MissionAssignmentRepository,
    PersonRepository,
)
from .dto import BadgeAwardDTO, BadgeDTO
from ._shared import BADGE_AWARD_POLICY, require_operator_id, transactional
from ..plugin_registry import PluginRegistry


class BadgeService:
    """Gestisce i badge e la propagazione degli award ai destinatari.

    L'enforcement primario resta al confine; il service ricontrolla le ACL
    quando riceve un operatore o un contesto frontend/CLI.
    """

    def __init__(
        self,
        badge_repo: BadgeRepository,
        badge_award_repo: BadgeAwardRepository,
        assignment_repo: MissionAssignmentRepository,
        activity_repo: ActivityRepository,
        person_repo: PersonRepository,
        acl_service=None,
        authorization_policy=None,
        plugin_registry: Optional[PluginRegistry] = None,
        event_publisher: Optional[EventPublisherPort] = None,
        uow=None,
    ) -> None:
        self._badge_repo = badge_repo
        self._badge_award_repo = badge_award_repo
        self._assignment_repo = assignment_repo
        self._activity_repo = activity_repo
        self._person_repo = person_repo
        self._acl_service = acl_service
        self._authz = authorization_policy
        self._plugin_registry = plugin_registry
        self._events = event_publisher
        self._uow = uow

    # ------------------------------------------------------------------
    # CRUD badge
    # ------------------------------------------------------------------

    @transactional
    def create(
        self,
        name: str,
        desc: str,
        image_url: Optional[str] = None,
        operator_id: Optional[UUID] = None,
    ) -> BadgeDTO:
        from ...domain.entities import Badge

        from ._shared import require_acl
        require_acl(self._authz, operator_id, Operation.CREATE_BADGE, SYSTEM_RESOURCE)
        if not name:
            raise ValidationError("name del badge è obbligatorio", field="name")
        if image_url is not None:
            parsed = urlparse(image_url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValidationError(
                    "image_url deve essere un URL http o https valido",
                    field="image_url",
                )
        _op_id = require_operator_id(operator_id)
        badge = Badge(id=uuid4(), name=name, description=desc, image_url=image_url)
        self._badge_repo.save(badge)
        if self._acl_service is not None:
            self._acl_service.on_resource_created(
                ResourceRef(ResourceType.BADGE, badge.id), _op_id
            )
        return BadgeDTO.from_badge(badge)

    @transactional
    def get(self, id: str, operator_id: Optional[UUID] = None) -> BadgeDTO:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.VIEW,
            ResourceRef(ResourceType.BADGE, UUID(id)),
        )
        badge = self._badge_repo.get(UUID(id))
        return BadgeDTO.from_badge(badge)

    @transactional
    def list(self, operator_id: Optional[UUID] = None) -> list[BadgeDTO]:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.LIST,
            ResourceRef.type_root(ResourceType.BADGE),
        )
        badges = self._badge_repo.list({})
        return [BadgeDTO.from_badge(b) for b in badges]

    # ------------------------------------------------------------------
    # award to assignment
    # ------------------------------------------------------------------

    @transactional
    def award_to_assignment(
        self,
        badge_id: str,
        assignment_id: str,
        operator_id: Optional[UUID] = None,
    ) -> BadgeAwardDTO:
        badge = self._badge_repo.get(UUID(badge_id))
        assignment = self._assignment_repo.get(UUID(assignment_id))
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.AWARD_BADGE,
            ResourceRef(ResourceType.ASSIGNMENT, assignment.id),
        )

        BADGE_AWARD_POLICY.validate_target_completed("assignment", assignment.status)
        BADGE_AWARD_POLICY.validate_no_duplicate_award(
            "ASSIGNMENT",
            assignment_id,
            self._badge_award_repo.exists_for_target("ASSIGNMENT", UUID(assignment_id)),
        )

        _op_id = require_operator_id(operator_id)
        if self._plugin_registry:
            ctx = HookContext(
                hook_point=HookPoint.BEFORE_AWARD_BADGE,
                operator_id=_op_id,
                payload={
                    "badge_id": badge_id,
                    "target_type": "ASSIGNMENT",
                    "target_id": assignment_id,
                },
            )
            self._plugin_registry.fire(HookPoint.BEFORE_AWARD_BADGE, ctx)

        # Calcolo destinatari
        if assignment.assignee_type == AssigneeType.GROUP:
            recipients = [
                p.id for p in self._person_repo.get_by_group(assignment.assignee_id)
            ]
            if not recipients:
                raise ValidationError(
                    f"Il gruppo {assignment.assignee_id} non ha membri: impossibile assegnare il badge"
                )
        elif assignment.assignee_type == AssigneeType.PERSON and assignment.assignee_id:
            recipients = [assignment.assignee_id]
        else:
            recipients = []

        if not recipients:
            raise ValidationError(
                "Impossibile assegnare un badge a un assignment senza destinatari"
            )

        award = BadgeAward(
            id=uuid4(),
            badge_id=badge.id,
            target_type="ASSIGNMENT",
            target_id=UUID(assignment_id),
            recipients=recipients,
            awarded_at=datetime.now(tz=timezone.utc),
        )
        try:
            self._badge_award_repo.save(award)
        except IntegrityError as exc:
            raise ValidationError(
                f"Esiste già un BadgeAward per l'assignment {assignment_id}"
            ) from exc
        assignment.award_badge(award)
        self._assignment_repo.save(assignment)

        if self._plugin_registry:
            ctx_after = HookContext(
                hook_point=HookPoint.AFTER_AWARD_BADGE,
                operator_id=_op_id,
                payload=ctx.payload,
                result=award,
            )
            self._plugin_registry.fire(HookPoint.AFTER_AWARD_BADGE, ctx_after)

        if self._events:
            self._events.publish(BadgeAwarded(
                occurred_at=award.awarded_at,
                badge_award_id=award.id,
                badge_id=badge.id,
                operator_id=_op_id,
                target_type="ASSIGNMENT",
                target_id=UUID(assignment_id),
                recipient_ids=tuple(recipients),
            ))

        return BadgeAwardDTO.from_award(award, badge)

    # ------------------------------------------------------------------
    # award to activity
    # ------------------------------------------------------------------

    @transactional
    def award_to_activity(
        self,
        badge_id: str,
        activity_id: str,
        operator_id: Optional[UUID] = None,
    ) -> BadgeAwardDTO:
        badge = self._badge_repo.get(UUID(badge_id))
        activity = self._activity_repo.get(UUID(activity_id))
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.AWARD_BADGE,
            ResourceRef(ResourceType.ACTIVITY, activity.id),
        )

        BADGE_AWARD_POLICY.validate_target_completed("attività", activity.status)
        BADGE_AWARD_POLICY.validate_no_duplicate_award(
            "ACTIVITY",
            activity_id,
            self._badge_award_repo.exists_for_target("ACTIVITY", UUID(activity_id)),
        )
        if not activity.assignees:
            raise ValidationError(
                "Impossibile assegnare un badge a un'attività senza assegnatari",
                field="assignees",
            )

        _op_id = require_operator_id(operator_id)
        if self._plugin_registry:
            ctx = HookContext(
                hook_point=HookPoint.BEFORE_AWARD_BADGE,
                operator_id=_op_id,
                payload={
                    "badge_id": badge_id,
                    "target_type": "ACTIVITY",
                    "target_id": activity_id,
                },
            )
            self._plugin_registry.fire(HookPoint.BEFORE_AWARD_BADGE, ctx)

        award = BadgeAward(
            id=uuid4(),
            badge_id=badge.id,
            target_type="ACTIVITY",
            target_id=UUID(activity_id),
            recipients=list(activity.assignees),
            awarded_at=datetime.now(tz=timezone.utc),
        )
        try:
            self._badge_award_repo.save(award)
        except IntegrityError as exc:
            raise ValidationError(
                f"Esiste già un BadgeAward per l'attività {activity_id}"
            ) from exc
        activity.badge_award = award
        self._activity_repo.save(activity)

        if self._plugin_registry:
            ctx_after = HookContext(
                hook_point=HookPoint.AFTER_AWARD_BADGE,
                operator_id=_op_id,
                payload=ctx.payload,
                result=award,
            )
            self._plugin_registry.fire(HookPoint.AFTER_AWARD_BADGE, ctx_after)

        if self._events:
            self._events.publish(BadgeAwarded(
                occurred_at=award.awarded_at,
                badge_award_id=award.id,
                badge_id=badge.id,
                operator_id=_op_id,
                target_type="ACTIVITY",
                target_id=UUID(activity_id),
                recipient_ids=tuple(award.recipients),
            ))

        return BadgeAwardDTO.from_award(award, badge)

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------

    @transactional
    def list_by_person(
        self, person_id: str, operator_id: Optional[UUID] = None
    ) -> list[BadgeAwardDTO]:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.VIEW,
            ResourceRef(ResourceType.PERSON, UUID(person_id)),
        )
        awards = self._badge_award_repo.get_by_person(UUID(person_id))
        result = []
        for award in awards:
            try:
                badge = self._badge_repo.get(award.badge_id)
            except Exception:
                badge = None
            result.append(BadgeAwardDTO.from_award(award, badge))
        return result
