# SPDX-License-Identifier: CC-BY-SA-4.0
from typing import Optional, Protocol, TypeVar, runtime_checkable
from uuid import UUID

from ..domain.acl import AclEntry, Operation, Profile, ResourceRef
from ..domain.entities import (
    Activity,
    Badge,
    BadgeAward,
    Group,
    Mission,
    MissionAssignment,
    Objective,
    Person,
)
from ..domain.enums import Status

T = TypeVar("T")


@runtime_checkable
class BaseRepository(Protocol[T]):
    def get(self, id: UUID) -> T: ...
    def list(self, filters: dict) -> list[T]: ...
    def save(self, entity: T) -> T: ...
    def delete(self, id: UUID) -> bool: ...
    def exists(self, id: UUID) -> bool: ...


@runtime_checkable
class MissionRepository(BaseRepository[Mission], Protocol):
    def get_by_title(self, title: str) -> Optional[Mission]: ...
    def get_for_update(self, id: UUID) -> Mission: ...


@runtime_checkable
class MissionAssignmentRepository(BaseRepository[MissionAssignment], Protocol):
    def get_by_mission(self, mission_id: UUID) -> list[MissionAssignment]: ...
    def get_by_assignee(self, assignee_id: UUID) -> list[MissionAssignment]: ...
    def get_by_status(self, status: Status) -> list[MissionAssignment]: ...
    def count_by_mission(self, mission_id: UUID) -> int: ...
    def count_active_by_mission(self, mission_id: UUID) -> int: ...


@runtime_checkable
class ObjectiveRepository(BaseRepository[Objective], Protocol):
    def get_by_assignment(self, assignment_id: UUID) -> list[Objective]: ...


@runtime_checkable
class ActivityRepository(BaseRepository[Activity], Protocol):
    def get_by_objective(self, objective_id: UUID) -> list[Activity]: ...
    def get_by_person(self, person_id: UUID) -> list[Activity]: ...


@runtime_checkable
class BadgeRepository(BaseRepository[Badge], Protocol):
    pass


@runtime_checkable
class BadgeAwardRepository(BaseRepository[BadgeAward], Protocol):
    def get_by_person(self, person_id: UUID) -> list[BadgeAward]: ...
    def get_by_assignment(self, assignment_id: UUID) -> Optional[BadgeAward]: ...
    def get_by_activity(self, activity_id: UUID) -> Optional[BadgeAward]: ...
    def exists_for_target(self, target_type: str, target_id: UUID) -> bool: ...


@runtime_checkable
class PersonRepository(BaseRepository[Person], Protocol):
    def get_by_group(self, group_id: UUID) -> list[Person]: ...
    def get_by_nickname(self, nickname: str) -> Optional[Person]: ...


@runtime_checkable
class GroupRepository(BaseRepository[Group], Protocol):
    def add_member(self, group_id: UUID, person_id: UUID) -> None: ...
    def remove_member(self, group_id: UUID, person_id: UUID) -> None: ...


@runtime_checkable
class AclEntryRepository(Protocol):
    """Porta di persistenza delle AclEntry (DESIGN §10).

    ``list_for`` restituisce le entry proprie di ``(risorsa, operazione)``:
    è la primitiva su cui AuthorizationPolicy costruisce match, precedenza ed
    ereditarietà. ``is_empty`` serve al seeding di bootstrap (una tantum).
    """

    def get(self, entry_id: UUID) -> Optional[AclEntry]: ...
    def list_for(self, resource: ResourceRef, operation: Operation) -> list[AclEntry]: ...
    def list_by_resource(self, resource: ResourceRef) -> list[AclEntry]: ...
    def list_all(self) -> list[AclEntry]: ...
    def save(self, entry: AclEntry) -> AclEntry: ...
    def delete(self, entry_id: UUID) -> bool: ...
    def delete_by_resource(self, resource: ResourceRef) -> None: ...
    def is_empty(self) -> bool: ...


@runtime_checkable
class ProfileProvider(Protocol):
    """Porta che risolve il Profile del richiedente (DESIGN §10).

    Per ``principal_id=None`` (richiedente non autenticato) restituisce il
    profilo anonimo implicito ``Profile.anonymous()``.
    """

    def profile_of(self, principal_id: Optional[UUID]) -> Profile: ...


@runtime_checkable
class ResourceHierarchyProvider(Protocol):
    """Porta che risolve i padri di una risorsa, per l'ereditarietà ACL."""

    def parents_of(self, resource: ResourceRef) -> list[ResourceRef]: ...
