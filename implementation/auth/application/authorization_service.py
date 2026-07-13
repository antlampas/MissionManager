# SPDX-License-Identifier: CC-BY-SA-4.0
"""Authorization facade over the active access-control model."""

from __future__ import annotations

from collections.abc import Mapping

from auth.domain.access_control import (
    AccessControlCapability,
    AuthorizationContext,
    Decision,
    DecisionTrace,
    ResourceRef,
    SubjectType,
    TYPE_ROOT_ID,
)
from auth.domain.errors import AuthorizationDenied, ValidationError
from auth.domain.identity import RequestIdentity
from auth.ports.audit import AuditLogger
from auth.ports.authorization import AccessControlModelRegistry, OperationCatalog, ProfileProvider


class AuthorizationService:
    def __init__(
        self,
        registry: AccessControlModelRegistry,
        profile_provider: ProfileProvider,
        operation_catalog: OperationCatalog,
        *,
        audit_logger: AuditLogger | None = None,
        environment: Mapping[str, object] | None = None,
    ) -> None:
        self._registry = registry
        self._profile_provider = profile_provider
        self._operation_catalog = operation_catalog
        self._audit_logger = audit_logger
        self._environment = dict(environment or {})

    def is_allowed(
        self,
        identity: RequestIdentity,
        operation: str,
        resource: ResourceRef,
        attrs: Mapping[str, object] | None = None,
    ) -> bool:
        try:
            self.require(identity, operation, resource, attrs)
        except AuthorizationDenied:
            return False
        return True

    def require(
        self,
        identity: RequestIdentity,
        operation: str,
        resource: ResourceRef,
        attrs: Mapping[str, object] | None = None,
    ) -> None:
        context = self._context(identity, operation, resource, attrs)
        if context.subject.type is SubjectType.PUBLIC and not context.operation_spec.read_only:
            self._audit_denied(context, "anonymous mutation denied")
            raise AuthorizationDenied("authorization denied")
        decision = self._registry.active().evaluate(context)
        if decision is not Decision.ALLOWED:
            self._audit_denied(context, "model denied")
            raise AuthorizationDenied("authorization denied")

    def candidate_resources(
        self,
        identity: RequestIdentity,
        operation: str,
        resource_type: str,
        attrs: Mapping[str, object] | None = None,
    ) -> list[ResourceRef]:
        model = self._registry.active()
        if AccessControlCapability.CANDIDATE_RESOURCES not in model.capabilities:
            raise ValidationError("active model does not support candidate resources")
        context = self._context(identity, operation, ResourceRef(resource_type, TYPE_ROOT_ID), attrs)
        return model.candidate_resources(context, resource_type)

    def explain(
        self,
        identity: RequestIdentity,
        operation: str,
        resource: ResourceRef,
        attrs: Mapping[str, object] | None = None,
    ) -> DecisionTrace:
        model = self._registry.active()
        if AccessControlCapability.EXPLAIN not in model.capabilities:
            raise ValidationError("active model does not support explanations")
        return model.explain(self._context(identity, operation, resource, attrs))

    def _context(
        self,
        identity: RequestIdentity,
        operation: str,
        resource: ResourceRef,
        attrs: Mapping[str, object] | None,
    ) -> AuthorizationContext:
        operation_spec = self._operation_catalog.get(operation)
        profile = self._profile_provider.profile_of(identity.subject)
        return AuthorizationContext(
            identity=identity,
            subject=identity.subject,
            profile=profile,
            operation=operation,
            operation_spec=operation_spec,
            resource=resource,
            request_attrs=dict(attrs or {}),
            environment=self._environment,
        )

    def _audit_denied(self, context: AuthorizationContext, reason: str) -> None:
        if self._audit_logger is None:
            return
        self._audit_logger.record(
            "AUTHZ_DENIED",
            subject=context.subject.type.value if context.subject.id is None else str(context.subject.id),
            operation=context.operation,
            resource_type=context.resource.type,
            resource_id=context.resource.id,
            reason=reason,
        )
