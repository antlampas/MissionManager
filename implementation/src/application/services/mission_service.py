# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from ...domain.acl import Operation, ResourceRef, SYSTEM_RESOURCE
from ...domain.entities import Activity, Mission, Objective
from ...domain.enums import ResourceType, Status
from ...domain.events import EventPublisherPort, MissionCreated, MissionDeleted
from ...domain.exceptions import NotFoundError, ValidationError
from ...domain.plugins import HookContext, HookPoint
from ...domain.repositories import MissionRepository
from ...domain.value_objects import AssignmentPolicy
from .dto import MissionDTO, ObjectiveDTO
from ._shared import require_operator_id, transactional
from ..plugin_registry import PluginRegistry


class MissionService:
    """Gestisce il ciclo di vita del blueprint Mission.

    Non gestisce assegnazioni né stato operativo: quelli sono compito
    di AssignmentService e ActivityService. L'enforcement primario resta al
    confine, ma il service ricontrolla le ACL quando riceve un operatore o un
    contesto frontend/CLI, come difesa in profondità.
    """

    def __init__(
        self,
        mission_repo: MissionRepository,
        acl_service=None,
        authorization_policy=None,
        plugin_registry: Optional[PluginRegistry] = None,
        event_publisher: Optional[EventPublisherPort] = None,
        assignment_repo=None,
        uow=None,
    ) -> None:
        self._mission_repo = mission_repo
        self._assignment_repo = assignment_repo
        self._acl_service = acl_service
        self._authz = authorization_policy
        self._plugin_registry = plugin_registry
        self._events = event_publisher
        self._uow = uow

    @transactional
    def create(
        self,
        title: str,
        desc: str,
        objectives: list[dict],
        operator_id: Optional[UUID] = None,
    ) -> MissionDTO:
        if not title or not title.strip() or len(title) > 255:
            raise ValidationError(
                "title è obbligatorio e deve avere al massimo 255 caratteri",
                field="title",
            )
        if len(desc) > 4096:
            raise ValidationError(
                "description deve avere al massimo 4096 caratteri", field="description"
            )
        if not objectives:
            raise ValidationError(
                "Una missione deve avere almeno un obiettivo", field="objectives"
            )
        for i, obj_data in enumerate(objectives):
            if not obj_data.get("activities"):
                raise ValidationError(
                    f"L'obiettivo {i} deve avere almeno un'attività",
                    field="objectives",
                )

        from ._shared import require_acl
        require_acl(self._authz, operator_id, Operation.CREATE_MISSION, SYSTEM_RESOURCE)
        _op_id = require_operator_id(operator_id)
        if self._plugin_registry:
            ctx = HookContext(
                hook_point=HookPoint.BEFORE_CREATE_MISSION,
                operator_id=_op_id,
                payload={"title": title, "desc": desc, "objectives": objectives},
            )
            self._plugin_registry.fire(HookPoint.BEFORE_CREATE_MISSION, ctx)

        mission_id = uuid4()
        objective_entities: list[Objective] = []
        for obj_data in objectives:
            obj_id = uuid4()
            activity_entities: list[Activity] = []
            for act_data in obj_data.get("activities", []):
                activity_entities.append(
                    Activity(
                        id=uuid4(),
                        title=act_data.get("title", ""),
                        description=act_data.get("description", ""),
                        status=Status.UNASSIGNED,
                        objective_id=obj_id,
                        assignees=[],
                    )
                )
            objective_entities.append(
                Objective(
                    id=obj_id,
                    description=obj_data.get("description", ""),
                    activities=activity_entities,
                    mission_id=mission_id,
                )
            )

        mission = Mission(
            id=mission_id,
            title=title,
            description=desc,
            assignment_policy=AssignmentPolicy.unlimited(),
            objectives=objective_entities,
        )
        mission.validate()
        self._mission_repo.save(mission)
        if self._acl_service is not None:
            self._acl_service.on_resource_created(
                ResourceRef(ResourceType.MISSION, mission_id), _op_id
            )

        if self._plugin_registry:
            ctx_after = HookContext(
                hook_point=HookPoint.AFTER_CREATE_MISSION,
                operator_id=_op_id,
                payload=ctx.payload,
                result=mission,
            )
            self._plugin_registry.fire(HookPoint.AFTER_CREATE_MISSION, ctx_after)

        if self._events:
            self._events.publish(MissionCreated(
                occurred_at=datetime.now(tz=timezone.utc),
                mission_id=mission_id,
                operator_id=_op_id,
                title=title,
            ))

        return MissionDTO.from_mission(mission)

    @transactional
    def get(self, id: str, operator_id: Optional[UUID] = None) -> MissionDTO:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.VIEW,
            ResourceRef(ResourceType.MISSION, UUID(id)),
        )
        mission = self._mission_repo.get(UUID(id))
        return MissionDTO.from_mission(mission)

    @transactional
    def list(
        self, filters: dict, operator_id: Optional[UUID] = None
    ) -> list[MissionDTO]:
        unknown = set(filters) - {"title"}
        if unknown:
            raise ValidationError(
                f"Filtri missione non supportati: {', '.join(sorted(unknown))}",
                field="filters",
            )
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.LIST,
            ResourceRef.type_root(ResourceType.MISSION),
        )
        missions = self._mission_repo.list(filters)
        return [MissionDTO.from_mission(m) for m in missions]

    # NB: il blueprint è immutabile dopo create() — non esiste add_objective né
    # alcuna modifica di obiettivi/attività a posteriori (vedi DESIGN §2.4).

    @transactional
    def delete(self, mission_id: str, operator_id: Optional[UUID] = None) -> None:
        op_id = require_operator_id(operator_id)
        uuid = UUID(mission_id)
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.DELETE,
            ResourceRef(ResourceType.MISSION, uuid),
        )
        if not self._mission_repo.exists(uuid):
            raise NotFoundError(
                f"Mission {mission_id} non trovata",
                resource_type="mission",
                resource_id=uuid,
            )
        # La cancellazione della missione elimina anche gli assignment figli:
        # la cascata ACL deve coprire pure le loro entry (es. il MANAGE_ACL
        # seminato al creatore), altrimenti restano orfane in mm_acl_entries.
        child_assignment_ids: list[UUID] = []
        if self._acl_service is not None and self._assignment_repo is not None:
            child_assignment_ids = [
                a.id for a in self._assignment_repo.get_by_mission(uuid)
            ]
        self._mission_repo.delete(uuid)
        if self._acl_service is not None:
            for assignment_id in child_assignment_ids:
                self._acl_service.on_resource_deleted(
                    ResourceRef(ResourceType.ASSIGNMENT, assignment_id)
                )
            self._acl_service.on_resource_deleted(
                ResourceRef(ResourceType.MISSION, uuid)
            )

        if self._events:
            self._events.publish(MissionDeleted(
                occurred_at=datetime.now(tz=timezone.utc),
                mission_id=uuid,
                operator_id=op_id,
            ))
