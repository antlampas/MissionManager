# SPDX-License-Identifier: CC-BY-SA-4.0
"""Uniform administration facade for active access-control extensions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol

from auth.domain.access_control import (
    AccessControlCapability,
    AccessControlModelExtension,
    ResourceRef,
    SubjectRef,
)
from auth.domain.errors import AuthorizationDenied, ValidationError
from auth.domain.identity import RequestIdentity
from auth.domain.policies import AccessControlModelSpec
from auth.ports.authorization import AccessControlModelRegistry


@dataclass(frozen=True)
class AccessControlArtifactDTO:
    id: str
    model_id: str
    data: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AccessControlArtifactInput:
    data: Mapping[str, object]


@dataclass(frozen=True)
class AccessControlArtifactPatch:
    data: Mapping[str, object]


class AccessControlExtensionAdminService(Protocol):
    model_id: str

    def list_artifacts(self, identity: RequestIdentity, scope: ResourceRef | None = None) -> list[AccessControlArtifactDTO]: ...

    def create_artifact(self, identity: RequestIdentity, input: AccessControlArtifactInput) -> AccessControlArtifactDTO: ...

    def update_artifact(self, identity: RequestIdentity, artifact_id: str, changes: AccessControlArtifactPatch) -> AccessControlArtifactDTO: ...

    def delete_artifact(self, identity: RequestIdentity, artifact_id: str) -> None: ...

    def delete_by_resource(self, resource: ResourceRef) -> None: ...

    def delete_by_subject(self, subject: SubjectRef) -> None: ...

    def on_resource_created(self, resource: ResourceRef, creator: SubjectRef, resource_type: str) -> None: ...

    def ensure_bootstrap_artifacts(self) -> None: ...


class AccessControlAdministrationService:
    def __init__(
        self,
        registry: AccessControlModelRegistry,
        admins: Mapping[str, AccessControlExtensionAdminService] | None = None,
    ) -> None:
        self._registry = registry
        self._admins = dict(admins or {})

    def active_model(self) -> AccessControlModelSpec:
        model = self._registry.active()
        return AccessControlModelSpec(
            id=model.id,
            capabilities=model.capabilities,
            required_providers=model.required_providers,
            admin_operations=model.admin_operations,
        )

    def list_policies(self, identity: RequestIdentity, resource: ResourceRef) -> list[AccessControlArtifactDTO]:
        return self._admin().list_artifacts(identity, resource)

    def create_policy(self, identity: RequestIdentity, input: AccessControlArtifactInput) -> AccessControlArtifactDTO:
        return self._admin().create_artifact(identity, input)

    def update_policy(self, identity: RequestIdentity, policy_id: str, changes: AccessControlArtifactPatch) -> AccessControlArtifactDTO:
        return self._admin().update_artifact(identity, policy_id, changes)

    def delete_policy(self, identity: RequestIdentity, policy_id: str) -> None:
        self._admin().delete_artifact(identity, policy_id)

    def on_resource_created(self, resource: ResourceRef, creator: SubjectRef, resource_type: str) -> None:
        self._admin().on_resource_created(resource, creator, resource_type)

    def ensure_bootstrap_policies(self) -> None:
        self._admin().ensure_bootstrap_artifacts()

    def _admin(self) -> AccessControlExtensionAdminService:
        model: AccessControlModelExtension = self._registry.active()
        if AccessControlCapability.ADMIN_API not in model.capabilities:
            raise AuthorizationDenied("active access-control model does not expose administration")
        admin = self._admins.get(model.id)
        if admin is None:
            raise ValidationError("active access-control admin service is not configured")
        return admin
