# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from ...domain.acl import Operation, ResourceRef
from ...domain.entities import Activity, MissionAssignment, Objective
from ...domain.enums import AssigneeType, ResourceType, Status
from ...domain.events import AssignmentCreated, AssignmentStatusChanged, EventPublisherPort
from ...domain.exceptions import NotFoundError, ValidationError
from ...domain.plugins import HookContext, HookPoint
from ...domain.repositories import (
    GroupRepository,
    MissionAssignmentRepository,
    MissionRepository,
    ObjectiveRepository,
    PersonRepository,
)
from .activity_service import ActivityService
from .dto import AssignmentDTO, PersonDTO
from ._shared import ASSIGNMENT_STATUS_POLICY, require_operator_id, transactional
from ..plugin_registry import PluginRegistry


class AssignmentService:
    """Orchestratore degli assignment: crea MissionAssignment dal blueprint,
    gestisce l'assegnatario e delega le transizioni di stato delle attività
    ad ActivityService.

    L'enforcement primario resta al confine; il service ricontrolla le ACL
    quando riceve un operatore o un contesto frontend/CLI.
    """

    def __init__(
        self,
        assignment_repo: MissionAssignmentRepository,
        mission_repo: MissionRepository,
        person_repo: PersonRepository,
        group_repo: GroupRepository,
        activity_svc: ActivityService,
        objective_repo: Optional[ObjectiveRepository] = None,
        acl_service=None,
        authorization_policy=None,
        plugin_registry: Optional[PluginRegistry] = None,
        event_publisher: Optional[EventPublisherPort] = None,
        uow=None,
    ) -> None:
        self._assignment_repo = assignment_repo
        self._mission_repo = mission_repo
        self._person_repo = person_repo
        self._group_repo = group_repo
        self._activity_svc = activity_svc
        self._objective_repo = objective_repo
        self._acl_service = acl_service
        self._authz = authorization_policy
        self._plugin_registry = plugin_registry
        self._events = event_publisher
        self._uow = uow

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------

    @transactional
    def create(
        self,
        mission_id: str,
        assignee_type: Optional[str] = None,
        assignee_id: Optional[str] = None,
        operator_id: Optional[UUID] = None,
    ) -> AssignmentDTO:
        mission_uuid = UUID(mission_id)
        mission = self._mission_repo.get_for_update(mission_uuid)
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.CREATE_ASSIGNMENT,
            ResourceRef(ResourceType.MISSION, mission_uuid),
        )

        # Verifica AssignmentPolicy — prima del hook
        policy = mission.assignment_policy
        if policy.max_total is not None:
            total = self._assignment_repo.count_by_mission(mission_uuid)
            if total >= policy.max_total:
                raise ValidationError(
                    f"Questa missione ha già raggiunto il limite di "
                    f"{policy.max_total} assegnazioni"
                )
        # assignee_type e assignee_id formano una coppia atomica.
        if (assignee_type is None) != (assignee_id is None):
            raise ValidationError(
                "assignee_type e assignee_id devono essere forniti insieme",
                field="assignee_id",
            )

        # Validazione assegnatario opzionale
        parsed_type: Optional[AssigneeType] = None
        parsed_id: Optional[UUID] = None
        if assignee_type and assignee_id:
            parsed_type = AssigneeType(assignee_type)
            parsed_id = UUID(assignee_id)
            self._validate_assignee(parsed_type, parsed_id)

        # UNASSIGNED è una bozza: non consuma max_concurrent. Il limite va
        # verificato solo se questa create produce un assignment operativo.
        if parsed_id is not None and policy.max_concurrent is not None:
            active = self._assignment_repo.count_active_by_mission(mission_uuid)
            if active >= policy.max_concurrent:
                raise ValidationError(
                    f"Questa missione ha già {active} assegnazioni attive "
                    f"(limite: {policy.max_concurrent})"
                )

        _op_id = require_operator_id(operator_id)
        if self._plugin_registry:
            ctx = HookContext(
                hook_point=HookPoint.BEFORE_CREATE_ASSIGNMENT,
                operator_id=_op_id,
                payload={
                    "mission_id": mission_id,
                    "assignee_type": assignee_type,
                    "assignee_id": assignee_id,
                },
            )
            self._plugin_registry.fire(HookPoint.BEFORE_CREATE_ASSIGNMENT, ctx)

        assignment_id = uuid4()
        initial_status = Status.ASSIGNED if parsed_id else Status.UNASSIGNED

        # Replica blueprint
        new_objectives: list[Objective] = []
        for bp_obj in mission.objectives:
            new_obj_id = uuid4()
            new_activities: list[Activity] = []
            for bp_act in bp_obj.activities:
                new_activities.append(
                    Activity(
                        id=uuid4(),
                        title=bp_act.title,
                        description=bp_act.description,
                        status=Status.UNASSIGNED,
                        objective_id=new_obj_id,
                        assignees=[],
                    )
                )
            new_objectives.append(
                Objective(
                    id=new_obj_id,
                    description=bp_obj.description,
                    assignment_id=assignment_id,
                    activities=new_activities,
                )
            )

        assignment = MissionAssignment(
            id=assignment_id,
            mission_id=mission_uuid,
            status=initial_status,
            objectives=new_objectives,
            assignee_type=parsed_type,
            assignee_id=parsed_id,
        )
        assignment.validate()
        self._assignment_repo.save(assignment)
        if self._acl_service is not None:
            self._acl_service.on_resource_created(
                ResourceRef(ResourceType.ASSIGNMENT, assignment_id), _op_id
            )

        if self._plugin_registry:
            ctx_after = HookContext(
                hook_point=HookPoint.AFTER_CREATE_ASSIGNMENT,
                operator_id=_op_id,
                payload=ctx.payload,
                result=assignment,
            )
            self._plugin_registry.fire(HookPoint.AFTER_CREATE_ASSIGNMENT, ctx_after)

        if self._events and parsed_type is not None and parsed_id is not None:
            self._events.publish(AssignmentCreated(
                occurred_at=datetime.now(tz=timezone.utc),
                assignment_id=assignment_id,
                mission_id=mission_uuid,
                operator_id=_op_id,
                assignee_type=parsed_type,
                assignee_id=parsed_id,
            ))

        return AssignmentDTO.from_assignment(assignment)

    # ------------------------------------------------------------------
    # assign
    # ------------------------------------------------------------------

    @transactional
    def assign(
        self,
        assignment_id: str,
        assignee_type: str,
        assignee_id: str,
        operator_id: Optional[UUID] = None,
    ) -> AssignmentDTO:
        op_id = require_operator_id(operator_id)
        assignment = self._assignment_repo.get(UUID(assignment_id))
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.ASSIGN,
            ResourceRef(ResourceType.ASSIGNMENT, assignment.id),
        )
        if assignment.status != Status.UNASSIGNED:
            raise ValidationError("L'assignment è già stato assegnato")

        parsed_type = AssigneeType(assignee_type)
        parsed_id = UUID(assignee_id)
        self._validate_assignee(parsed_type, parsed_id)

        mission = self._mission_repo.get_for_update(assignment.mission_id)
        policy = mission.assignment_policy
        if policy.max_concurrent is not None:
            active = self._assignment_repo.count_active_by_mission(assignment.mission_id)
            if active >= policy.max_concurrent:
                raise ValidationError(
                    f"Questa missione ha già {active} assegnazioni attive "
                    f"(limite: {policy.max_concurrent})"
                )

        assignment.assign_to(parsed_type, parsed_id)
        assignment.validate()
        self._assignment_repo.save(assignment)
        if self._events:
            self._events.publish(AssignmentCreated(
                occurred_at=datetime.now(tz=timezone.utc),
                assignment_id=assignment.id,
                mission_id=assignment.mission_id,
                operator_id=op_id,
                assignee_type=parsed_type,
                assignee_id=parsed_id,
            ))
        return AssignmentDTO.from_assignment(assignment)

    # ------------------------------------------------------------------
    # get / list / update_status / delete
    # ------------------------------------------------------------------

    @transactional
    def get(self, id: str, operator_id: Optional[UUID] = None) -> AssignmentDTO:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.VIEW,
            ResourceRef(ResourceType.ASSIGNMENT, UUID(id)),
        )
        assignment = self._assignment_repo.get(UUID(id))
        return AssignmentDTO.from_assignment(assignment)

    @transactional
    def list(
        self, mission_id: str, filters: dict, operator_id: Optional[UUID] = None
    ) -> list[AssignmentDTO]:
        unknown = set(filters) - {"status"}
        if unknown:
            raise ValidationError(
                f"Filtri assignment non supportati: {', '.join(sorted(unknown))}",
                field="filters",
            )
        status_filter: Optional[Status] = None
        raw_status = filters.get("status")
        if raw_status:
            try:
                status_filter = Status(str(raw_status).upper())
            except ValueError:
                raise ValidationError(
                    f"Stato sconosciuto: {raw_status!r}", field="status"
                ) from None
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.LIST,
            ResourceRef(ResourceType.MISSION, UUID(mission_id)),
        )
        assignments = self._assignment_repo.get_by_mission(UUID(mission_id))
        if status_filter is not None:
            assignments = [a for a in assignments if a.status == status_filter]
        return [AssignmentDTO.from_assignment(a) for a in assignments]

    @transactional
    def list_activity_candidates(
        self, assignment_id: str, operator_id: Optional[UUID] = None
    ) -> dict[str, list[PersonDTO]]:
        """Candidati assegnabili per ciascuna attività dell'assignment (perimetro DESIGN §2.4).

        Perimetro: assignment di GRUPPO → i membri del gruppo; di PERSONA → solo quella
        persona; ancora UNASSIGNED → chiunque (il dominio non vincola). Per ogni attività
        si escludono gli assegnatari correnti.

        È il **pre-filtro di presentazione** che i frontend usano per offrire solo persone
        ammesse; l'enforcement effettivo resta in ``ActivityService.assign_to``
        (``ACTIVITY_ASSIGNMENT_POLICY.validate_person_in_assignment``). La regola di
        perimetro vive così nel layer applicativo, non nei frontend.
        """
        assignment = self._assignment_repo.get(UUID(assignment_id))
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.VIEW,
            ResourceRef(ResourceType.ASSIGNMENT, assignment.id),
        )

        if assignment.assignee_type == AssigneeType.GROUP and assignment.assignee_id:
            perimeter = self._person_repo.get_by_group(assignment.assignee_id)
        elif assignment.assignee_type == AssigneeType.PERSON and assignment.assignee_id:
            perimeter = [
                p for p in self._person_repo.list({}) if p.id == assignment.assignee_id
            ]
        else:
            perimeter = self._person_repo.list({})

        candidates: dict[str, list[PersonDTO]] = {}
        for objective in assignment.objectives:
            for activity in objective.activities:
                already = set(activity.assignees)
                candidates[str(activity.id)] = [
                    PersonDTO.from_person(p) for p in perimeter if p.id not in already
                ]
        return candidates

    @transactional
    def update_status(
        self,
        assignment_id: str,
        status: str,
        operator_id: Optional[UUID] = None,
    ) -> AssignmentDTO:
        assignment = self._assignment_repo.get(UUID(assignment_id))
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.UPDATE_STATUS,
            ResourceRef(ResourceType.ASSIGNMENT, assignment.id),
        )
        new_status = Status(status)
        ASSIGNMENT_STATUS_POLICY.validate_transition(assignment.status, new_status)
        if new_status == Status.COMPLETED:
            ASSIGNMENT_STATUS_POLICY.validate_assignment_completion(
                assignment.compute_outcome()
            )

        _op_id = require_operator_id(operator_id)
        old_status = assignment.status
        if self._plugin_registry:
            ctx = HookContext(
                hook_point=HookPoint.BEFORE_UPDATE_STATUS,
                operator_id=_op_id,
                payload={
                    "entity_id": assignment_id,
                    "entity_type": "ASSIGNMENT",
                    "new_status": status,
                },
            )
            self._plugin_registry.fire(HookPoint.BEFORE_UPDATE_STATUS, ctx)

        assignment.update_status(new_status)
        self._assignment_repo.save(assignment)

        if self._plugin_registry:
            ctx_after = HookContext(
                hook_point=HookPoint.AFTER_UPDATE_STATUS,
                operator_id=_op_id,
                payload=ctx.payload,
                result=assignment,
            )
            self._plugin_registry.fire(HookPoint.AFTER_UPDATE_STATUS, ctx_after)

        if self._events:
            self._events.publish(AssignmentStatusChanged(
                occurred_at=datetime.now(tz=timezone.utc),
                assignment_id=UUID(assignment_id),
                operator_id=_op_id,
                old_status=old_status,
                new_status=new_status,
            ))

        return AssignmentDTO.from_assignment(assignment)

    @transactional
    def delete(
        self,
        assignment_id: str,
        operator_id: Optional[UUID] = None,
    ) -> None:
        require_operator_id(operator_id)
        uuid = UUID(assignment_id)
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.DELETE,
            ResourceRef(ResourceType.ASSIGNMENT, uuid),
        )
        if not self._assignment_repo.exists(uuid):
            raise NotFoundError(
                f"Assignment {assignment_id} non trovato",
                resource_type="assignment",
                resource_id=uuid,
            )
        self._assignment_repo.delete(uuid)
        if self._acl_service is not None:
            self._acl_service.on_resource_deleted(
                ResourceRef(ResourceType.ASSIGNMENT, uuid)
            )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _validate_assignee(self, assignee_type: AssigneeType, assignee_id: UUID) -> None:
        if assignee_type == AssigneeType.PERSON:
            if not self._person_repo.exists(assignee_id):
                raise NotFoundError(
                    f"Person {assignee_id} non trovata",
                    resource_type="person",
                    resource_id=assignee_id,
                )
        elif assignee_type == AssigneeType.GROUP:
            if not self._group_repo.exists(assignee_id):
                raise NotFoundError(
                    f"Group {assignee_id} non trovato",
                    resource_type="group",
                    resource_id=assignee_id,
                )
