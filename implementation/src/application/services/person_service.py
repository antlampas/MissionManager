# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from ...domain.acl import Operation, Profile, ResourceRef, SYSTEM_RESOURCE
from ...domain.entities import Group, Person, Zone
from ...domain.enums import ResourceType, ZoneType
from ...domain.exceptions import NotFoundError, ValidationError
from ...domain.repositories import GroupRepository, PersonRepository
from .dto import GroupDTO, PersonDTO
from ..plugin_registry import PluginRegistry
from ._shared import transactional


class PersonService:
    """Gestisce il ciclo di vita di Person e Group nel dominio.

    In modalità OIDC, save() e delete() chiamano le API admin
    dell'identity provider tramite l'adapter concreto del Layer 3.

    La gestione del profilo ACL (livello e gruppi) è un'operazione separata
    (:meth:`set_acl_profile`): l'assegnazione dei profili vive fuori dal
    catalogo delegabile (DESIGN §10) — al confine è protetta da
    ``MANAGE_PROFILES`` su ``SYSTEM:global`` — e una persona appena creata
    nasce con il profilo meno privilegiato.
    """

    def __init__(
        self,
        person_repo: PersonRepository,
        group_repo: GroupRepository,
        authorization_policy=None,
        plugin_registry: Optional[PluginRegistry] = None,
        acl_service=None,
        uow=None,
    ) -> None:
        self._person_repo = person_repo
        self._group_repo = group_repo
        self._authz = authorization_policy
        self._plugin_registry = plugin_registry
        self._acl_service = acl_service
        self._uow = uow

    # ------------------------------------------------------------------
    # Person
    # ------------------------------------------------------------------

    @transactional
    def add(self, nicknames: list[str], operator_id: Optional[UUID] = None) -> PersonDTO:
        from ._shared import require_acl
        require_acl(self._authz, operator_id, Operation.CREATE_PERSON, SYSTEM_RESOURCE)
        nicknames = self._normalize_nicknames(nicknames)
        if not nicknames:
            raise ValidationError(
                "Almeno un nickname non vuoto è obbligatorio", field="nicknames"
            )
        person = Person(id=uuid4(), nicknames=nicknames, acl=Profile())
        person.validate()
        self._person_repo.save(person)
        return PersonDTO.from_person(person)

    @transactional
    def update(
        self,
        id: str,
        nicknames: Optional[list[str]] = None,
        operator_id: Optional[UUID] = None,
    ) -> PersonDTO:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.EDIT,
            ResourceRef(ResourceType.PERSON, UUID(id)),
        )
        person = self._person_repo.get(UUID(id))
        if nicknames is not None:
            person.nicknames = self._normalize_nicknames(nicknames)
        person.validate()
        self._person_repo.save(person)
        return PersonDTO.from_person(person)

    @transactional
    def set_acl_profile(
        self,
        id: str,
        acl_level: Optional[int] = None,
        acl_groups: Optional[list[str]] = None,
        operator_id: Optional[UUID] = None,
    ) -> PersonDTO:
        """Imposta livello e/o gruppi del profilo ACL di una persona.

        I parametri lasciati a ``None`` conservano il valore corrente; una
        lista vuota di gruppi rimuove tutti i gruppi espliciti (resta il
        gruppo universale implicito ``public``).
        """
        from ._shared import require_acl
        require_acl(self._authz, operator_id, Operation.MANAGE_PROFILES, SYSTEM_RESOURCE)
        person = self._person_repo.get(UUID(id))
        new_level = acl_level if acl_level is not None else person.acl.level
        if acl_groups is not None:
            new_groups = frozenset(acl_groups)
        else:
            new_groups = person.acl.groups
        person.acl = Profile(level=new_level, groups=new_groups)
        person.validate()
        self._person_repo.save(person)
        return PersonDTO.from_person(person)

    @transactional
    def remove_acl_group(
        self, id: str, group: str, operator_id: Optional[UUID] = None
    ) -> PersonDTO:
        """Toglie la persona da un singolo gruppo ACL."""
        from ._shared import require_acl
        require_acl(self._authz, operator_id, Operation.MANAGE_PROFILES, SYSTEM_RESOURCE)
        person = self._person_repo.get(UUID(id))
        remaining = person.acl.groups - {str(group).strip()}
        person.acl = Profile(level=person.acl.level, groups=remaining)
        self._person_repo.save(person)
        return PersonDTO.from_person(person)

    @transactional
    def remove(self, id: str, operator_id: Optional[UUID] = None) -> None:
        uuid = UUID(id)
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.DELETE,
            ResourceRef(ResourceType.PERSON, uuid),
        )
        if not self._person_repo.exists(uuid):
            raise NotFoundError(
                f"Person {id} non trovata",
                resource_type="person",
                resource_id=uuid,
            )
        self._person_repo.delete(uuid)
        # Cascata sui soggetti: le entry USER(id) della persona rimossa non
        # devono restare orfane nel repository ACL.
        if self._acl_service is not None:
            self._acl_service.on_subject_deleted(uuid)

    @transactional
    def get(self, id: str, operator_id: Optional[UUID] = None) -> PersonDTO:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.VIEW,
            ResourceRef(ResourceType.PERSON, UUID(id)),
        )
        person = self._person_repo.get(UUID(id))
        return PersonDTO.from_person(person)

    @transactional
    def list(
        self, filters: dict, operator_id: Optional[UUID] = None
    ) -> list[PersonDTO]:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.LIST,
            ResourceRef.type_root(ResourceType.PERSON),
        )
        return [PersonDTO.from_person(p) for p in self._person_repo.list(filters)]

    @transactional
    def list_by_group(
        self, group_id: str, operator_id: Optional[UUID] = None
    ) -> list[PersonDTO]:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.VIEW,
            ResourceRef(ResourceType.GROUP, UUID(group_id)),
        )
        persons = self._person_repo.get_by_group(UUID(group_id))
        return [PersonDTO.from_person(p) for p in persons]

    # ------------------------------------------------------------------
    # Group
    # ------------------------------------------------------------------

    @transactional
    def add_group(
        self,
        name: Optional[str] = None,
        zone_type: Optional[str] = None,
        zone_description: Optional[str] = None,
        operator_id: Optional[UUID] = None,
    ) -> GroupDTO:
        from ._shared import require_acl
        require_acl(self._authz, operator_id, Operation.CREATE_GROUP, SYSTEM_RESOURCE)
        zone = self._build_zone(
            zone_id=uuid4(),
            name=name,
            zone_type=zone_type,
            zone_description=zone_description,
        )
        group = Group(id=uuid4(), zone=zone)
        group.validate()
        self._group_repo.save(group)
        return GroupDTO.from_group(group)

    @transactional
    def update_group(
        self,
        group_id: str,
        name: Optional[str] = None,
        zone_type: Optional[str] = None,
        zone_description: Optional[str] = None,
        operator_id: Optional[UUID] = None,
    ) -> GroupDTO:
        uuid = UUID(group_id)
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.EDIT,
            ResourceRef(ResourceType.GROUP, uuid),
        )
        group = self._group_repo.get(uuid)
        if name is None and zone_type is None and zone_description is None:
            return GroupDTO.from_group(group)

        current = group.zone
        group.zone = self._build_zone(
            zone_id=current.id if current else uuid4(),
            name=name if name is not None else (current.name if current else None),
            zone_type=zone_type if zone_type is not None else (
                current.type.value if current else None
            ),
            zone_description=(
                zone_description
                if zone_description is not None
                else (current.description if current else None)
            ),
        )
        group.validate()
        self._group_repo.save(group)
        return GroupDTO.from_group(group)

    @transactional
    def remove_group(self, group_id: str, operator_id: Optional[UUID] = None) -> None:
        uuid = UUID(group_id)
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.DELETE,
            ResourceRef(ResourceType.GROUP, uuid),
        )
        if not self._group_repo.exists(uuid):
            raise NotFoundError(
                f"Group {group_id} non trovato",
                resource_type="group",
                resource_id=uuid,
            )
        self._group_repo.delete(uuid)

    @transactional
    def get_group(self, group_id: str, operator_id: Optional[UUID] = None) -> GroupDTO:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.VIEW,
            ResourceRef(ResourceType.GROUP, UUID(group_id)),
        )
        group = self._group_repo.get(UUID(group_id))
        return GroupDTO.from_group(group)

    @transactional
    def list_groups(self, operator_id: Optional[UUID] = None) -> list[GroupDTO]:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.LIST,
            ResourceRef.type_root(ResourceType.GROUP),
        )
        return [GroupDTO.from_group(g) for g in self._group_repo.list({})]

    @transactional
    def add_group_member(
        self, group_id: str, person_id: str, operator_id: Optional[UUID] = None
    ) -> None:
        group_uuid = UUID(group_id)
        person_uuid = UUID(person_id)
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.MANAGE_MEMBERS,
            ResourceRef(ResourceType.GROUP, group_uuid),
        )
        if not self._group_repo.exists(group_uuid):
            raise NotFoundError(
                f"Group {group_id} non trovato",
                resource_type="group",
                resource_id=group_uuid,
            )
        if not self._person_repo.exists(person_uuid):
            raise NotFoundError(
                f"Person {person_id} non trovata",
                resource_type="person",
                resource_id=person_uuid,
            )
        try:
            self._group_repo.add_member(group_uuid, person_uuid)
        except ValueError as exc:
            raise ValidationError(str(exc), field="person_id") from None

    @transactional
    def remove_group_member(
        self, group_id: str, person_id: str, operator_id: Optional[UUID] = None
    ) -> None:
        from ._shared import require_acl
        require_acl(
            self._authz,
            operator_id,
            Operation.MANAGE_MEMBERS,
            ResourceRef(ResourceType.GROUP, UUID(group_id)),
        )
        self._group_repo.remove_member(UUID(group_id), UUID(person_id))

    @staticmethod
    def _normalize_nicknames(nicknames: list[str]) -> list[str]:
        normalized: list[str] = []
        for nickname in nicknames:
            if nickname is None:
                continue
            text = str(nickname).strip()
            if text:
                normalized.append(text)
        return normalized

    @staticmethod
    def _build_zone(
        zone_id: UUID,
        name: Optional[str],
        zone_type: Optional[str],
        zone_description: Optional[str],
    ) -> Optional[Zone]:
        clean_name = str(name).strip() if name is not None else ""
        clean_type = str(zone_type).strip() if zone_type is not None else ""
        clean_description = (
            str(zone_description).strip() if zone_description is not None else None
        )
        if clean_description == "":
            clean_description = None
        if not (clean_name or clean_type or clean_description):
            return None
        if not clean_name:
            raise ValidationError(
                "Nome gruppo obbligatorio quando si configura la zona",
                field="name",
            )
        try:
            resolved_type = ZoneType(clean_type) if clean_type else ZoneType.VIRTUAL
        except ValueError as exc:
            raise ValidationError(
                "zone_type deve essere GEOGRAPHIC o VIRTUAL",
                field="zone_type",
            ) from exc
        zone = Zone(
            id=zone_id,
            type=resolved_type,
            name=clean_name,
            description=clean_description,
        )
        zone.validate()
        return zone
