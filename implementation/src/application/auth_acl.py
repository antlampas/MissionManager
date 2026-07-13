# SPDX-License-Identifier: CC-BY-SA-4.0
"""Bridge that registers the reusable ACL engine as an Auth model."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping
from uuid import UUID

from acl.application.authorization_policy import AuthorizationPolicy as ACLAuthorizationPolicy
from acl.domain import Decision as ACLDecision
from acl.domain import ResourceRef as ACLResourceRef
from acl.domain import SubjectRef as ACLSubjectRef
from auth.domain.access_control import (
    AccessControlCapability,
    AuthorizationContext,
    Decision as AuthDecision,
    DecisionTrace as AuthDecisionTrace,
    OperationSpec as AuthOperationSpec,
    ResourceRef as AuthResourceRef,
    SubjectRef as AuthSubjectRef,
    SubjectType as AuthSubjectType,
)
from auth.domain.identity import AuthMethod, RequestIdentity
from auth.domain.profile import AuthorizationProfile
from auth.domain.types import AccountId


class ACLAccessControlModel:
    """Auth access-control model backed by ``antlampas/ACL``."""

    id = "acl"
    capabilities = frozenset(
        {
            AccessControlCapability.CANDIDATE_RESOURCES,
            AccessControlCapability.EXPLAIN,
        }
    )
    required_providers = frozenset()
    admin_operations = frozenset({"MANAGE_ACL"})

    def __init__(self, policy: ACLAuthorizationPolicy) -> None:
        self._policy = policy

    def evaluate(self, context: AuthorizationContext) -> AuthDecision:
        decision = self._policy.is_allowed(
            _acl_subject(context.subject),
            _operation_name(context.operation),
            _acl_resource(context.resource),
        )
        if decision == ACLDecision.ALLOWED:
            return AuthDecision.ALLOWED
        return AuthDecision.DENIED

    def candidate_resources(
        self,
        context: AuthorizationContext,
        resource_type: str,
    ) -> list[AuthResourceRef]:
        return [
            _auth_resource(resource)
            for resource in self._policy.candidate_resources(
                _acl_subject(context.subject),
                _operation_name(context.operation),
                resource_type,
            )
        ]

    def explain(self, context: AuthorizationContext) -> AuthDecisionTrace:
        trace = self._policy.explain(
            _acl_subject(context.subject),
            _operation_name(context.operation),
            _acl_resource(context.resource),
        )
        decision = (
            AuthDecision.ALLOWED
            if trace.decision == ACLDecision.ALLOWED
            else AuthDecision.DENIED
        )
        return AuthDecisionTrace(
            decision=decision,
            reason=trace.reason,
            model_id=self.id,
            matched_artifacts=tuple(str(entry_id) for entry_id in trace.matched_entry_ids),
        )

    def validate_config(self, settings: Mapping[str, object]) -> None:
        return None


class AuthOperationCatalogAdapter:
    """Expose MissionManager ACL operations through Auth's catalog port."""

    def __init__(self, acl_catalog) -> None:
        self._acl_catalog = acl_catalog

    def get(self, operation: str) -> AuthOperationSpec:
        spec = self._acl_catalog.require(_operation_name(operation))
        return AuthOperationSpec(
            name=spec.name,
            read_only=spec.read_only,
            inheritable=spec.inheritable,
            protected=spec.protected,
        )


class AuthProfileProviderAdapter:
    """Expose ACL authorization profiles through Auth's profile port."""

    def __init__(self, acl_profiles) -> None:
        self._acl_profiles = acl_profiles

    def profile_of(self, subject: AuthSubjectRef) -> AuthorizationProfile:
        profile = self._acl_profiles.profile_of(_acl_subject(subject))
        version = getattr(profile, "version", None)
        return AuthorizationProfile(
            id=None,
            level=int(getattr(profile, "level")),
            groups=frozenset(getattr(profile, "groups", frozenset()) or frozenset()),
            version=0 if version is None else int(version),
        )


def identity_from_principal(principal_id: UUID | str | None) -> RequestIdentity:
    """Build the Auth request identity used by MissionManager frontends."""

    if principal_id is None:
        return RequestIdentity.anonymous()
    account_id = AccountId(str(principal_id))
    return RequestIdentity(
        subject=AuthSubjectRef.user(account_id),
        account_id=account_id,
        auth_method=AuthMethod.ASSERTED,
        authenticated_at=datetime.now(timezone.utc),
    )


def _acl_subject(subject: AuthSubjectRef) -> ACLSubjectRef:
    if subject.type is AuthSubjectType.PUBLIC:
        return ACLSubjectRef.public()
    if subject.type is AuthSubjectType.USER:
        return ACLSubjectRef.user(str(subject.id))
    if subject.type is AuthSubjectType.SERVICE:
        return ACLSubjectRef.service(str(subject.id))
    raise ValueError(f"unsupported Auth subject type: {subject.type!r}")


def _acl_resource(resource: AuthResourceRef) -> ACLResourceRef:
    return ACLResourceRef(resource.type, resource.id)


def _auth_resource(resource: ACLResourceRef) -> AuthResourceRef:
    return AuthResourceRef(resource.type, resource.id)


def _operation_name(operation: str) -> str:
    return str(operation).strip().upper()
