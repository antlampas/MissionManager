# SPDX-License-Identifier: CC-BY-SA-4.0
"""Authorization adapter backed by the reusable ``acl`` package."""
from __future__ import annotations

from contextlib import nullcontext
from typing import Optional
from uuid import UUID

from acl.application.authorization_policy import AuthorizationPolicy as ACLAuthorizationPolicy
from auth.application.access_control_registry import DefaultAccessControlModelRegistry
from auth.application.authorization_service import AuthorizationService as AuthAuthorizationService

from .auth_acl import (
    ACLAccessControlModel,
    AuthOperationCatalogAdapter,
    AuthProfileProviderAdapter,
    identity_from_principal,
)
from ..domain.acl import (
    Operation,
    ResourceRef,
    SubjectType,
    from_external_resource,
    missionmanager_operation_catalog,
    to_external_resource,
)
from auth.domain.access_control import ResourceRef as AuthResourceRef


class AuthorizationPolicy:
    """Compatibility facade for MissionManager callers.

    MissionManager historically calls ``is_allowed`` with an optional UUID. The
    effective decision now flows through Auth's ``AuthorizationService`` with the
    external ACL engine registered as the active access-control model.
    """

    def __init__(
        self,
        entry_repo,
        profile_provider,
        hierarchy_provider,
        uow=None,
        operation_catalog=None,
    ) -> None:
        self._uow = uow
        self._catalog = operation_catalog or missionmanager_operation_catalog()
        entry_repo = _EntryRepositoryAdapter(entry_repo)
        profile_provider = _ProfileProviderAdapter(profile_provider)
        hierarchy_provider = _HierarchyProviderAdapter(hierarchy_provider)
        self._entries = entry_repo
        self._profiles = profile_provider
        self._hierarchy = hierarchy_provider
        self._policy = ACLAuthorizationPolicy(
            entry_repo,
            profile_provider,
            hierarchy_provider,
            self._catalog,
        )
        self._access_control_model = ACLAccessControlModel(self._policy)
        self._registry = DefaultAccessControlModelRegistry(
            active_model_id=self._access_control_model.id,
            models=[self._access_control_model],
        )
        self._authz = AuthAuthorizationService(
            registry=self._registry,
            profile_provider=AuthProfileProviderAdapter(profile_provider),
            operation_catalog=AuthOperationCatalogAdapter(self._catalog),
        )

    @property
    def external_policy(self) -> ACLAuthorizationPolicy:
        return self._policy

    @property
    def auth_authorization_service(self) -> AuthAuthorizationService:
        return self._authz

    @property
    def access_control_model(self) -> ACLAccessControlModel:
        return self._access_control_model

    @property
    def operation_catalog(self):
        return self._catalog

    @property
    def profile_provider(self):
        return self._profiles

    @property
    def entry_repository(self):
        return self._entries

    def is_allowed(
        self,
        principal_id: Optional[UUID],
        operation: Operation | str,
        resource: ResourceRef,
    ) -> bool:
        context = self._uow.transaction() if self._uow is not None else nullcontext()
        with context:
            return self._authz.is_allowed(
                identity_from_principal(principal_id),
                _operation_name(operation),
                _auth_resource(resource),
            )

    def explain(self, principal_id: Optional[UUID], operation: Operation | str, resource: ResourceRef):
        return self._authz.explain(
            identity_from_principal(principal_id),
            _operation_name(operation),
            _auth_resource(resource),
        )

    def candidate_resources(
        self,
        principal_id: Optional[UUID],
        operation: Operation | str,
        resource_type: str,
    ) -> list[ResourceRef]:
        return [
            from_external_resource(resource)
            for resource in self._authz.candidate_resources(
                identity_from_principal(principal_id),
                _operation_name(operation),
                resource_type,
            )
        ]


class _EntryRepositoryAdapter:
    def __init__(self, repo) -> None:
        self._repo = repo

    def entries_for(self, resource, operation: str):
        if hasattr(self._repo, "entries_for"):
            return self._external_entries(self._repo.entries_for(resource, operation))
        return self._external_entries(
            self._repo.list_for(from_external_resource(resource), _operation(operation))
        )

    def list_by_operation(self, operation: str, resource_type: str):
        if hasattr(self._repo, "list_by_operation"):
            return self._external_entries(self._repo.list_by_operation(operation, resource_type))
        return self._external_entries([
            entry for entry in self._repo.list_all()
            if _operation_name(entry.operation) == operation.strip().upper()
            and from_external_resource(entry.resource).type_value == resource_type.strip().upper()
        ])

    def list_by_resource(self, resource):
        return self._external_entries(self._repo.list_by_resource(from_external_resource(resource)))

    def get(self, entry_id):
        entry = self._repo.get(entry_id)
        return self._external_entry(entry) if entry is not None else None

    def list_all(self):
        return self._external_entries(self._repo.list_all())

    def save(self, entry):
        return self._repo.save(entry)

    def delete(self, entry_id):
        return self._repo.delete(entry_id)

    def replace_entries(self, resource, entries):
        return self._repo.replace_entries(from_external_resource(resource), entries)

    def delete_by_resource(self, resource):
        return self._repo.delete_by_resource(from_external_resource(resource))

    def delete_by_subject(self, subject):
        return self._repo.delete_by_subject(subject)

    def is_empty(self):
        return self._repo.is_empty()

    @staticmethod
    def _external_entry(entry):
        return entry.to_external() if hasattr(entry, "to_external") else entry

    @classmethod
    def _external_entries(cls, entries):
        return [cls._external_entry(entry) for entry in entries]

    def __getattr__(self, name: str):
        return getattr(self._repo, name)


class _ProfileProviderAdapter:
    def __init__(self, provider) -> None:
        self._provider = provider

    def profile_of(self, subject):
        if subject is None or getattr(subject, "type", None) == SubjectType.PUBLIC:
            return self._provider.profile_of(None)
        subject_id = getattr(subject, "id", subject)
        try:
            return self._provider.profile_of(UUID(str(subject_id)))
        except (TypeError, ValueError):
            return self._provider.profile_of(subject_id)


class _HierarchyProviderAdapter:
    def __init__(self, provider) -> None:
        self._provider = provider

    def parents_of(self, resource):
        return [
            to_external_resource(parent)
            for parent in self._provider.parents_of(from_external_resource(resource))
        ]


def _operation(operation: str) -> Operation | str:
    try:
        return Operation(operation.strip().upper())
    except ValueError:
        return operation.strip().upper()


def _operation_name(operation: Operation | str) -> str:
    return str(operation.value if isinstance(operation, Operation) else operation).strip().upper()


def _auth_resource(resource: ResourceRef) -> AuthResourceRef:
    return AuthResourceRef(resource.type_value, resource.key())
