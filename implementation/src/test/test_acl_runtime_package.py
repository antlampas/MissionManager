# SPDX-License-Identifier: CC-BY-SA-4.0
"""Regressioni sul package runtime ``acl`` standalone.

Copre il modello ACL framework-neutral: bootstrap, policy, servizio di gestione,
normalizzazione richieste e adapter di persistenza.
"""

from __future__ import annotations

import pytest

from acl.adapters.identity.resolver import ContextIdentityResolver, StaticIdentityResolver
from acl.adapters.requests.context import InvocationContext
from acl.adapters.requests.denied_mapper import DictDeniedResponseMapper
from acl.adapters.requests.normalizer import MappingRequestNormalizer, RequestMappingRule
from acl.application import (
    ACLEntryInput,
    AuthorizationRequest,
    BootstrapACLConfig,
    InitialAdminInput,
    SeedRule,
    SeedingPolicy,
)
from acl.bootstrap.factory import create_acl_container
from acl.domain import (
    ACLEntry,
    ACLEntryId,
    ACLValidationError,
    AuthenticationRequired,
    AuthorizationDenied,
    Decision,
    GrantConstraintError,
    JoinOp,
    OperationUnknownError,
    Permission,
    Profile,
    ResourceMappingError,
    ResourceRef,
    SubjectRef,
)
from acl.infrastructure.persistence import JsonFileACLEntryRepository
from acl.ports import RequestIdentity


def _identity(subject: SubjectRef) -> RequestIdentity:
    return RequestIdentity(subject=subject, authenticated=subject != SubjectRef.public(), auth_method="test")


def test_bootstrap_seeds_global_admin_and_public_read_roots():
    container = create_acl_container()
    admin = SubjectRef.user("admin")

    container.bootstrap.ensure_bootstrap_entries(
        BootstrapACLConfig(
            resource_roots=frozenset({"mission"}),
            public_read_roots=frozenset({"mission"}),
        )
    )
    container.bootstrap.create_initial_admin(InitialAdminInput(admin, level=0, groups=frozenset({"admins"})))

    mission = ResourceRef.concrete("mission", "m1")
    assert container.policy.is_allowed(SubjectRef.public(), "VIEW", mission) == Decision.ALLOWED
    assert container.policy.is_allowed(SubjectRef.public(), "EDIT", mission) == Decision.DENIED
    assert container.policy.is_allowed(admin, "MANAGE_ACL", ResourceRef.system()) == Decision.ALLOWED

    with pytest.raises(AuthorizationDenied):
        container.authorization.require(
            AuthorizationRequest(_identity(SubjectRef.user("operator")), "MANAGE_ACL", ResourceRef.system())
        )

    event_types = [event.type for event in container.audit.events()]
    assert "BOOTSTRAP_COMPLETED" in event_types
    assert "INITIAL_ADMIN_CREATED" in event_types


def test_policy_prefers_own_explicit_deny_and_lists_matching_candidates():
    alice = SubjectRef.user("alice")
    mission = ResourceRef.concrete("mission", "m1")
    root = ResourceRef.type_root("mission")
    container = create_acl_container(profiles={alice: Profile(level=50, groups=frozenset())})
    container.entries.save(
        ACLEntry(
            ACLEntryId("root-view"),
            SubjectRef.public(),
            root,
            "view",
            Permission.ALLOW,
            level=100,
        )
    )
    container.entries.save(
        ACLEntry(
            ACLEntryId("mission-deny"),
            alice,
            mission,
            "view",
            Permission.DENY,
            level=100,
        )
    )

    trace = container.policy.explain(alice, "VIEW", mission)

    assert trace.decision == Decision.DENIED
    assert trace.explicit_deny is True
    assert trace.reason == "own_explicit_deny"
    assert trace.matched_entry_ids == (ACLEntryId("mission-deny"),)
    assert container.policy.candidate_resources(alice, "VIEW", "mission") == [root]


def test_acl_service_manages_entries_and_blocks_protected_grants_without_global_manage():
    admin = SubjectRef.user("admin")
    bob = SubjectRef.user("bob")
    mission = ResourceRef.concrete("mission", "m1")
    container = create_acl_container(
        profiles={
            admin: Profile(level=0, groups=frozenset({"admins"})),
            bob: Profile(level=50, groups=frozenset()),
        }
    )
    container.bootstrap.ensure_bootstrap_entries(BootstrapACLConfig())
    admin_identity = _identity(admin)
    bob_identity = _identity(bob)

    view_entry = container.acl.create_entry(
        admin_identity,
        ACLEntryInput(
            subject=bob,
            resource=mission,
            operation="view",
            permission=Permission.ALLOW,
            level=50,
        ),
    )
    container.acl.create_entry(
        admin_identity,
        ACLEntryInput(
            subject=bob,
            resource=mission,
            operation="MANAGE_ACL",
            permission=Permission.ALLOW,
            level=50,
        ),
    )

    entry_ids = {entry.id for entry in container.acl.list_entries(admin_identity, mission)}
    assert view_entry.id in entry_ids
    assert container.policy.is_allowed(bob, "VIEW", mission) == Decision.ALLOWED

    with pytest.raises(GrantConstraintError, match="protected operation"):
        container.acl.create_entry(
            bob_identity,
            ACLEntryInput(
                subject=bob,
                resource=mission,
                operation="EXECUTE",
                permission=Permission.ALLOW,
                level=50,
            ),
        )


def test_resource_creation_seeding_grants_creator_permissions():
    creator = SubjectRef.user("creator")
    mission = ResourceRef.concrete("mission", "created")
    container = create_acl_container(
        profiles={creator: Profile(level=25, groups=frozenset({"ops"}))},
        seeding_policy=SeedingPolicy(
            enabled=True,
            rules={
                "MISSION": SeedRule(
                    resource_type="mission",
                    operations=frozenset({"view", "edit"}),
                    grant_to="CREATOR",
                    level_strategy="CREATOR_LEVEL",
                )
            },
        ),
    )

    container.acl.on_resource_created(mission, creator, "mission")

    entries = container.entries.list_by_resource(mission)
    assert {entry.operation for entry in entries} == {"EDIT", "VIEW"}
    assert {entry.subject for entry in entries} == {creator}
    assert {entry.level for entry in entries} == {25}
    assert container.policy.is_allowed(creator, "EDIT", mission) == Decision.ALLOWED
    assert container.policy.is_allowed(SubjectRef.public(), "VIEW", mission) == Decision.DENIED


def test_json_repository_roundtrips_entries_and_flushes_deletes(tmp_path):
    path = tmp_path / "acl.json"
    entry = ACLEntry(
        ACLEntryId("entry-1"),
        SubjectRef.public(),
        ResourceRef.concrete("mission", "m1"),
        "view",
        Permission.ALLOW,
        level=None,
        group="ops",
        profile_join=JoinOp.AND,
    )

    repo = JsonFileACLEntryRepository(path)
    repo.save(entry)

    reloaded = JsonFileACLEntryRepository(path)
    assert reloaded.get(entry.id) == entry

    reloaded.delete_by_subject(SubjectRef.public())
    assert JsonFileACLEntryRepository(path).all_entries() == []


class _Binding:
    def bind(self, principal_id: str) -> SubjectRef | None:
        return SubjectRef.user(f"bound-{principal_id}")


def test_request_normalizer_identity_resolvers_and_denied_mapper_fail_closed():
    identity = _identity(SubjectRef.user("alice"))
    normalizer = MappingRequestNormalizer(
        [
            RequestMappingRule(
                selector="missions.detail",
                operation="view",
                resource_type="mission",
                resource_id_source="mission_id",
            )
        ],
        fallback_rule=RequestMappingRule(
            selector="fallback",
            operation="MANAGE_ACL",
            fallback_protected=True,
        ),
    )
    context = InvocationContext(
        selector="missions.detail",
        resource_ids={"mission_id": "m1"},
        identity=identity,
    )

    request = normalizer.authorization_request(context, identity)
    assert request.operation == "VIEW"
    assert request.resource == ResourceRef("MISSION", "m1")
    assert normalizer.candidate_resources_request(context, identity).resource_type == "MISSION"
    assert normalizer.authorization_request({"selector": "unknown"}, identity).resource == ResourceRef.system()

    with pytest.raises(ResourceMappingError):
        MappingRequestNormalizer([]).authorization_request({"selector": "unknown"}, identity)
    with pytest.raises(ResourceMappingError):
        MappingRequestNormalizer([RequestMappingRule("system", "VIEW")]).candidate_resources_request(
            {"selector": "system"},
            identity,
        )

    assert StaticIdentityResolver(identity).resolve(context) == identity
    assert ContextIdentityResolver().resolve(context) == identity
    bound = ContextIdentityResolver(_Binding()).resolve(InvocationContext("x", principal_id="external"))
    assert bound.subject == SubjectRef.user("bound-external")

    mapper = DictDeniedResponseMapper()
    assert mapper.map_error(AuthenticationRequired())["status"] == 401
    assert mapper.map_error(AuthorizationDenied())["status"] == 403
    assert mapper.map_error(ACLValidationError("bad"))["code"] == "acl_validation_error"
    assert mapper.map_error(OperationUnknownError("bad"))["code"] == "operation_unknown"
    assert mapper.map_error(ResourceMappingError("bad"))["code"] == "resource_mapping_error"
