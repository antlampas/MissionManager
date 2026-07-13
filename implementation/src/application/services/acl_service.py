# SPDX-License-Identifier: CC-BY-SA-4.0
"""ACL management adapter backed by the reusable ``acl`` package."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional
from uuid import UUID, uuid4

from acl.application.acl_service import ACLService as ExternalACLService
from acl.application.dto import (
    ACLEntryInput,
    ACLEntryPatch,
    SeedRule,
    SeedingPolicy as ExternalSeedingPolicy,
)
from acl.domain import (
    ACLEntry as ExternalACLEntry,
    ACLEntryId,
    ACLEntryInvariants,
    ACLValidationError,
    ANON_SENTINEL,
    GrantConstraintError,
    JoinOp,
    OperationUnknownError,
    Permission,
)
from acl.ports import RequestIdentity

from ...domain.acl import (
    Operation,
    ResourceRef,
    SubjectRef,
    SYSTEM_RESOURCE,
    missionmanager_operation_catalog,
    to_external_resource,
    to_external_subject,
)
from ...domain.enums import ResourceType
from ...domain.exceptions import ForbiddenError, NotFoundError, ValidationError
from ._shared import transactional
from .dto import AclEntryDTO


@dataclass(frozen=True)
class SeedingPolicy:
    """MissionManager resource-creation seeding configuration."""

    enabled: bool = True
    operations_by_type: Mapping[ResourceType, tuple[Operation, ...]] = field(
        default_factory=lambda: {
            ResourceType.MISSION: (Operation.MANAGE_ACL,),
            ResourceType.ASSIGNMENT: (Operation.MANAGE_ACL,),
            ResourceType.BADGE: (Operation.MANAGE_ACL,),
        }
    )

    def to_external(self) -> ExternalSeedingPolicy:
        return ExternalSeedingPolicy(
            enabled=self.enabled,
            rules={
                resource_type.value: SeedRule(
                    resource_type=resource_type.value,
                    operations=frozenset(operation.value for operation in operations),
                    grant_to="CREATOR",
                    level_strategy="UNIVERSAL",
                )
                for resource_type, operations in self.operations_by_type.items()
            },
        )


class AclService:
    def __init__(
        self,
        entry_repo,
        authorization,
        seeding_policy: Optional[SeedingPolicy] = None,
        uow=None,
    ) -> None:
        self._entries = entry_repo
        self._authz = authorization
        self._operations = getattr(
            authorization, "operation_catalog", missionmanager_operation_catalog()
        )
        self._external = ExternalACLService(
            entries=getattr(authorization, "entry_repository", entry_repo),
            policy=authorization.external_policy,
            profiles=authorization.profile_provider,
            operations=self._operations,
            uow=uow,
            seeding_policy=(seeding_policy or SeedingPolicy()).to_external(),
        )
        self._uow = uow
        self._invariants = ACLEntryInvariants()

    @transactional
    def list_entries(
        self,
        resource_type: str,
        resource_id: str,
        operator_id: Optional[UUID] = None,
    ) -> list[AclEntryDTO]:
        resource = self._resource(resource_type, resource_id)
        return self._convert_many(
            self._call(
                self._external.list_entries,
                self._identity(operator_id),
                to_external_resource(resource),
            )
        )

    @transactional
    def list_all_entries(self, operator_id: Optional[UUID] = None) -> list[AclEntryDTO]:
        if not self._authz.is_allowed(operator_id, Operation.MANAGE_ACL, SYSTEM_RESOURCE):
            raise ForbiddenError("Non autorizzato a gestire le ACL del sistema")
        return [AclEntryDTO.from_entry(entry) for entry in self._entries.list_all()]

    @transactional
    def create_entry(
        self,
        resource_type: str,
        resource_id: str,
        operation: str,
        permission: str,
        subject_id: Optional[str] = None,
        level: Optional[int] = None,
        group: Optional[str] = None,
        profile_join: str = "OR",
        subject_join: str = "AND",
        operator_id: Optional[UUID] = None,
    ) -> AclEntryDTO:
        input_dto = ACLEntryInput(
            subject=to_external_subject(self._subject(subject_id)),
            resource=to_external_resource(self._resource(resource_type, resource_id)),
            operation=self._operation(operation).value,
            permission=self._permission(permission),
            level=self._coerce_level(level),
            group=self._coerce_group(group),
            profile_join=self._join(profile_join, "profile_join"),
            subject_join=self._join(subject_join, "subject_join"),
        )
        return AclEntryDTO.from_entry(
            self._call(self._external.create_entry, self._identity(operator_id), input_dto)
        )

    @transactional
    def update_entry(
        self,
        entry_id: str,
        permission: Optional[str] = None,
        level: Optional[int] = None,
        group: Optional[str] = None,
        clear_level: bool = False,
        clear_group: bool = False,
        operator_id: Optional[UUID] = None,
    ) -> AclEntryDTO:
        patch = ACLEntryPatch(
            permission=self._permission(permission) if permission else None,
            level=self._coerce_level(level) if level is not None else None,
            group=self._coerce_group(group) if group is not None else None,
            clear_level=clear_level,
            clear_group=clear_group,
        )
        return AclEntryDTO.from_entry(
            self._call(
                self._external.update_entry,
                self._identity(operator_id),
                ACLEntryId(str(entry_id)),
                patch,
            )
        )

    @transactional
    def delete_entry(self, entry_id: str, operator_id: Optional[UUID] = None) -> None:
        self._call(
            self._external.delete_entry,
            self._identity(operator_id),
            ACLEntryId(str(entry_id)),
        )

    def on_resource_created(self, resource: ResourceRef, creator_id: UUID) -> None:
        self._call(
            self._external.on_resource_created,
            to_external_resource(resource),
            to_external_subject(SubjectRef.user(creator_id)),
            resource.type_value,
        )

    def on_resource_deleted(self, resource: ResourceRef) -> None:
        self._call(self._external.delete_by_resource, to_external_resource(resource))

    def on_subject_deleted(self, principal_id: UUID) -> None:
        """Cascata sui soggetti: rimuove le entry ``USER(principal_id)``.

        Invocata alla cancellazione di una persona, così le sue entry non
        restano orfane in ``mm_acl_entries`` (gli UUID non vengono riusati,
        ma accumulerebbero rumore nella gestione ACL).
        """
        self._entries.delete_by_subject(
            to_external_subject(SubjectRef.user(principal_id))
        )

    @transactional
    def ensure_bootstrap_entries(
        self, read_threshold: int, write_threshold: int, admin_threshold: int
    ) -> None:
        if not self._entries.is_empty():
            return

        mission_root = ResourceRef.type_root(ResourceType.MISSION)
        badge_root = ResourceRef.type_root(ResourceType.BADGE)
        person_root = ResourceRef.type_root(ResourceType.PERSON)
        group_root = ResourceRef.type_root(ResourceType.GROUP)

        defaults: list[tuple[ResourceRef, Operation, int]] = [
            (mission_root, Operation.VIEW, read_threshold),
            (mission_root, Operation.LIST, read_threshold),
            (mission_root, Operation.DELETE, write_threshold),
            (mission_root, Operation.CREATE_ASSIGNMENT, write_threshold),
            (mission_root, Operation.ASSIGN, write_threshold),
            (mission_root, Operation.UPDATE_STATUS, write_threshold),
            (mission_root, Operation.AWARD_BADGE, write_threshold),
            (mission_root, Operation.MANAGE_ACL, admin_threshold),
            (badge_root, Operation.VIEW, read_threshold),
            (badge_root, Operation.LIST, read_threshold),
            (badge_root, Operation.MANAGE_ACL, admin_threshold),
            (person_root, Operation.VIEW, read_threshold),
            (person_root, Operation.LIST, read_threshold),
            (person_root, Operation.EDIT, admin_threshold),
            (person_root, Operation.DELETE, admin_threshold),
            (person_root, Operation.MANAGE_ACL, admin_threshold),
            (group_root, Operation.VIEW, read_threshold),
            (group_root, Operation.LIST, read_threshold),
            (group_root, Operation.EDIT, admin_threshold),
            (group_root, Operation.DELETE, admin_threshold),
            (group_root, Operation.MANAGE_MEMBERS, admin_threshold),
            (group_root, Operation.MANAGE_ACL, admin_threshold),
            (SYSTEM_RESOURCE, Operation.VIEW, read_threshold),
            (SYSTEM_RESOURCE, Operation.LIST, read_threshold),
            (SYSTEM_RESOURCE, Operation.CREATE_MISSION, write_threshold),
            (SYSTEM_RESOURCE, Operation.CREATE_BADGE, write_threshold),
            (SYSTEM_RESOURCE, Operation.EXECUTE, write_threshold),
            (SYSTEM_RESOURCE, Operation.CREATE_PERSON, admin_threshold),
            (SYSTEM_RESOURCE, Operation.CREATE_GROUP, admin_threshold),
            (SYSTEM_RESOURCE, Operation.MANAGE_PROFILES, admin_threshold),
            (SYSTEM_RESOURCE, Operation.MANAGE_ACL, admin_threshold),
        ]
        for resource, operation, threshold in defaults:
            entry = ExternalACLEntry(
                id=ACLEntryId(str(uuid4())),
                subject=to_external_subject(SubjectRef.public()),
                resource=to_external_resource(resource),
                operation=operation.value,
                permission=Permission.ALLOW,
                level=threshold,
            )
            spec = self._operations.require(entry.operation)
            self._invariants.validate(entry, spec)
            self._entries.save(entry)

    def _call(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except GrantConstraintError as exc:
            raise ForbiddenError(str(exc)) from exc
        except (ACLValidationError, OperationUnknownError, ValueError) as exc:
            if isinstance(exc, ACLValidationError) and "does not exist" in str(exc):
                raise NotFoundError(
                    "Entry ACL non trovata",
                    resource_type="acl_entry",
                ) from exc
            raise ValidationError(str(exc)) from exc

    @staticmethod
    def _convert_many(entries) -> list[AclEntryDTO]:
        return [AclEntryDTO.from_entry(entry) for entry in entries]

    @staticmethod
    def _identity(operator_id: Optional[UUID]) -> RequestIdentity:
        if operator_id is None:
            return RequestIdentity.anonymous(auth_method="missionmanager")
        return RequestIdentity(
            subject=to_external_subject(SubjectRef.user(operator_id)),
            authenticated=True,
            auth_method="missionmanager",
            principal_id=str(operator_id),
        )

    @staticmethod
    def _resource(resource_type: str, resource_id: str) -> ResourceRef:
        try:
            rtype: ResourceType | str = ResourceType(str(resource_type).upper())
        except ValueError:
            raise ValidationError(
                f"Tipo di risorsa sconosciuto: {resource_type!r}", field="resource_type"
            )
        raw = str(resource_id).strip()
        if not raw:
            raise ValidationError("resource_id è obbligatorio", field="resource_id")
        return ResourceRef(rtype, raw)

    @staticmethod
    def _subject(subject_id: Optional[str]) -> SubjectRef:
        if subject_id in (None, ""):
            return SubjectRef.public()
        return SubjectRef.user(str(subject_id))

    @staticmethod
    def _operation(operation: str) -> Operation:
        try:
            return Operation(str(operation).upper())
        except ValueError:
            raise ValidationError(
                f"Operazione ACL sconosciuta: {operation!r}", field="operation"
            )

    @staticmethod
    def _permission(permission: str) -> Permission:
        try:
            return Permission(str(permission).upper())
        except ValueError:
            raise ValidationError(
                "Il permesso deve essere ALLOW o DENY", field="permission"
            )

    @staticmethod
    def _coerce_level(level: Optional[int]) -> Optional[int]:
        if level in (None, ""):
            return None
        try:
            value = int(level)
        except (TypeError, ValueError):
            raise ValidationError("Il livello ACL deve essere un intero", field="level")
        if value < 0 or value > ANON_SENTINEL:
            raise ValidationError(
                "Il livello ACL deve essere compreso tra 0 e ANON_SENTINEL",
                field="level",
            )
        return value

    @staticmethod
    def _coerce_group(group: Optional[str]) -> Optional[str]:
        if group is None:
            return None
        value = str(group).strip()
        return value or None

    @staticmethod
    def _join(value: str, field_name: str) -> JoinOp:
        try:
            return JoinOp(str(value).upper())
        except ValueError:
            raise ValidationError(
                f"{field_name} deve essere AND o OR", field=field_name
            )
