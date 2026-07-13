# SPDX-License-Identifier: CC-BY-SA-4.0
"""Adapter del sistema ACL (DESIGN §10): profilo del richiedente e gerarchia.

- :class:`PersonProfileProvider` implementa la porta ``ProfileProvider``:
  risolve il ``Profile`` dell'operatore dal ``PersonRepository`` e restituisce
  il profilo anonimo implicito per i richiedenti non autenticati o sconosciuti.
- :class:`MissionResourceHierarchyProvider` implementa la porta
  ``ResourceHierarchyProvider``: la catena strutturale è
  ``ACTIVITY → OBJECTIVE → (ASSIGNMENT | MISSION)`` e ``ASSIGNMENT → MISSION``;
  ogni risorsa concreta risale infine alla radice del proprio tipo (``TYPE:*``,
  con l'albero operativo radicato in ``MISSION:*``), dove il bootstrap semina
  le soglie di default. ``SYSTEM:global`` non ha padri.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from ..domain.acl import Profile, ResourceRef, SubjectType, from_external_resource
from ..domain.enums import ResourceType
from ..domain.exceptions import NotFoundError
from ..domain.repositories import (
    ActivityRepository,
    MissionAssignmentRepository,
    ObjectiveRepository,
    PersonRepository,
)


class PersonProfileProvider:
    def __init__(self, person_repo: PersonRepository) -> None:
        self._persons = person_repo

    def profile_of(self, principal_id) -> Profile:
        if principal_id is None:
            return Profile.anonymous()
        if hasattr(principal_id, "subject"):
            principal_id = principal_id.subject
        if hasattr(principal_id, "type"):
            if principal_id.type == SubjectType.PUBLIC:
                return Profile.anonymous()
            principal_id = principal_id.id
        try:
            return self._persons.get(UUID(str(principal_id))).acl
        except (NotFoundError, ValueError, TypeError):
            return Profile.anonymous()


# Radice gerarchica dell'albero operativo: assignment, obiettivi e attività
# risalgono a MISSION:* dove vivono le soglie di default operative.
_OPERATIONAL_TYPES = (
    ResourceType.MISSION,
    ResourceType.ASSIGNMENT,
    ResourceType.OBJECTIVE,
    ResourceType.ACTIVITY,
)


class MissionResourceHierarchyProvider:
    def __init__(
        self,
        assignment_repo: MissionAssignmentRepository,
        objective_repo: ObjectiveRepository,
        activity_repo: ActivityRepository,
    ) -> None:
        self._assignments = assignment_repo
        self._objectives = objective_repo
        self._activities = activity_repo

    def parents_of(self, resource: ResourceRef) -> list[ResourceRef]:
        resource = from_external_resource(resource)
        if resource.type == ResourceType.SYSTEM:
            return []
        if resource.is_type_root:
            if resource.type in _OPERATIONAL_TYPES and resource.type != ResourceType.MISSION:
                return [ResourceRef.type_root(ResourceType.MISSION)]
            return []

        structural = self._structural_parent(resource)
        if structural is not None:
            return [structural]
        # Risorsa senza padre strutturale (o non più risolvibile): si ricade
        # sulla radice del tipo, così le soglie di default restano applicabili.
        return [ResourceRef.type_root(resource.type)]

    def _structural_parent(self, resource: ResourceRef) -> Optional[ResourceRef]:
        try:
            resource_id = UUID(resource.key())
        except ValueError:
            return None

        try:
            if resource.type == ResourceType.ASSIGNMENT:
                assignment = self._assignments.get(resource_id)
                return ResourceRef(ResourceType.MISSION, assignment.mission_id)
            if resource.type == ResourceType.OBJECTIVE:
                objective = self._objectives.get(resource_id)
                if objective.assignment_id is not None:
                    return ResourceRef(ResourceType.ASSIGNMENT, objective.assignment_id)
                if objective.mission_id is not None:
                    return ResourceRef(ResourceType.MISSION, objective.mission_id)
            if resource.type == ResourceType.ACTIVITY:
                activity = self._activities.get(resource_id)
                return ResourceRef(ResourceType.OBJECTIVE, activity.objective_id)
        except NotFoundError:
            return None
        return None
