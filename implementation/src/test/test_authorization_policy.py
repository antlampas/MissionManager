# SPDX-License-Identifier: CC-BY-SA-4.0
"""AuthorizationPolicy: precedenza, ereditarietà, ambito di sistema (DESIGN §10).

La policy è pura e dipende solo dalle porte: qui è verificata con adapter
in-memory, senza persistenza reale.
"""
from uuid import uuid4

from auth.domain.access_control import AccessControlCapability

from src.application.authorization import AuthorizationPolicy
from src.domain.acl import (
    ANON_SENTINEL,
    SYSTEM_RESOURCE,
    AclEntry,
    JoinOp,
    Operation,
    Permission,
    Profile,
    ResourceRef,
    SubjectRef,
)
from src.domain.enums import ResourceType


class _InMemoryEntryRepo:
    def __init__(self, entries=()):
        self._entries = {e.id: e for e in entries}

    def get(self, entry_id):
        return self._entries.get(entry_id)

    def list_for(self, resource, operation):
        return [
            e for e in self._entries.values()
            if e.resource == resource and e.operation == operation
        ]

    def list_by_resource(self, resource):
        return [e for e in self._entries.values() if e.resource == resource]

    def list_all(self):
        return list(self._entries.values())

    def save(self, entry):
        self._entries[entry.id] = entry
        return entry

    def delete(self, entry_id):
        return self._entries.pop(entry_id, None) is not None

    def delete_by_resource(self, resource):
        for eid in [e.id for e in self._entries.values() if e.resource == resource]:
            self._entries.pop(eid)

    def is_empty(self):
        return not self._entries


class _StaticProfiles:
    def __init__(self, profiles):
        self._profiles = profiles

    def profile_of(self, principal_id):
        if principal_id is None:
            return Profile.anonymous()
        return self._profiles.get(principal_id, Profile.anonymous())


class _StaticHierarchy:
    def __init__(self, parents=None):
        self._parents = parents or {}

    def parents_of(self, resource):
        return self._parents.get((resource.type, resource.key()), [])


def _allow(resource, operation, level=None, group=None, subject=None, join=JoinOp.OR):
    return AclEntry(
        id=uuid4(),
        subject=subject or SubjectRef.public(),
        resource=resource,
        operation=operation,
        permission=Permission.ALLOW,
        level=level,
        group=group,
        profile_join=join,
    )


def _deny(resource, operation, level=None, group=None):
    return AclEntry(
        id=uuid4(),
        subject=SubjectRef.public(),
        resource=resource,
        operation=operation,
        permission=Permission.DENY,
        level=level,
        group=group,
    )


def _policy(entries, profiles, parents=None):
    return AuthorizationPolicy(
        entry_repo=_InMemoryEntryRepo(entries),
        profile_provider=_StaticProfiles(profiles),
        hierarchy_provider=_StaticHierarchy(parents),
    )


MISSION = ResourceRef(ResourceType.MISSION, uuid4())


def test_default_deny_without_entries():
    operator = uuid4()
    policy = _policy([], {operator: Profile(level=0)})
    assert policy.is_allowed(operator, Operation.VIEW, MISSION) is False


def test_acl_is_registered_as_active_auth_model():
    policy = _policy([], {})
    model = policy.access_control_model

    assert model.id == "acl"
    assert policy.auth_authorization_service is not None
    assert AccessControlCapability.EXPLAIN in model.capabilities
    assert "MANAGE_ACL" in model.admin_operations


def test_allow_by_level_threshold():
    operator = uuid4()
    policy = _policy(
        [_allow(MISSION, Operation.VIEW, level=100)],
        {operator: Profile(level=50)},
    )
    assert policy.is_allowed(operator, Operation.VIEW, MISSION) is True
    assert policy.is_allowed(None, Operation.VIEW, MISSION) is False  # anonimo


def test_deny_wins_over_allow():
    operator = uuid4()
    policy = _policy(
        [
            _allow(MISSION, Operation.VIEW, level=100),
            _deny(MISSION, Operation.VIEW, group="banned"),
        ],
        {operator: Profile(level=10, groups=frozenset({"banned"}))},
    )
    assert policy.is_allowed(operator, Operation.VIEW, MISSION) is False


def test_public_read_grant_reaches_anonymous():
    policy = _policy([_allow(MISSION, Operation.VIEW, group="public")], {})
    assert policy.is_allowed(None, Operation.VIEW, MISSION) is True


def test_child_inherits_from_parent_when_it_has_no_own_entries():
    activity = ResourceRef(ResourceType.ACTIVITY, uuid4())
    operator = uuid4()
    policy = _policy(
        [_allow(MISSION, Operation.UPDATE_STATUS, level=50)],
        {operator: Profile(level=50)},
        parents={(ResourceType.ACTIVITY, activity.key()): [MISSION]},
    )
    assert policy.is_allowed(operator, Operation.UPDATE_STATUS, activity) is True


def test_own_entries_suppress_inheritance():
    activity = ResourceRef(ResourceType.ACTIVITY, uuid4())
    alice, bob = uuid4(), uuid4()
    policy = _policy(
        [
            _allow(MISSION, Operation.VIEW, level=100),
            # entry propria dell'attività: solo Alice
            _allow(
                activity, Operation.VIEW,
                subject=SubjectRef.user(alice), level=ANON_SENTINEL,
            ),
        ],
        {alice: Profile(level=100), bob: Profile(level=100)},
        parents={(ResourceType.ACTIVITY, activity.key()): [MISSION]},
    )
    assert policy.is_allowed(alice, Operation.VIEW, activity) is True
    # Bob soddisferebbe la soglia del padre, ma le entry proprie esauriscono
    # la decisione: default deny.
    assert policy.is_allowed(bob, Operation.VIEW, activity) is False


def test_multi_parent_deny_precedence():
    child = ResourceRef(ResourceType.OBJECTIVE, uuid4())
    parent_a = ResourceRef(ResourceType.MISSION, uuid4())
    parent_b = ResourceRef(ResourceType.MISSION, uuid4())
    operator = uuid4()
    policy = _policy(
        [
            _deny(parent_a, Operation.VIEW, level=100),
            _allow(parent_b, Operation.VIEW, level=100),
        ],
        {operator: Profile(level=50)},
        parents={(ResourceType.OBJECTIVE, child.key()): [parent_a, parent_b]},
    )
    # Il package ACL integrato applica deny-override anche tra padri diversi.
    assert policy.is_allowed(operator, Operation.VIEW, child) is False


def test_manage_acl_does_not_inherit():
    assignment = ResourceRef(ResourceType.ASSIGNMENT, uuid4())
    operator = uuid4()
    policy = _policy(
        [_allow(MISSION, Operation.MANAGE_ACL, level=100)],
        {operator: Profile(level=0)},
        parents={(ResourceType.ASSIGNMENT, assignment.key()): [MISSION]},
    )
    assert policy.is_allowed(operator, Operation.MANAGE_ACL, assignment) is False
    assert policy.is_allowed(operator, Operation.MANAGE_ACL, MISSION) is True


def test_system_scope_rules():
    operator, other = uuid4(), uuid4()
    policy = _policy(
        [_allow(SYSTEM_RESOURCE, Operation.CREATE_MISSION, level=50, group="creators")],
        {
            operator: Profile(level=99, groups=frozenset({"creators"})),
            other: Profile(level=99),
        },
    )
    # livello OR gruppo (profile_join di default)
    assert policy.is_allowed(operator, Operation.CREATE_MISSION, SYSTEM_RESOURCE) is True
    assert policy.is_allowed(other, Operation.CREATE_MISSION, SYSTEM_RESOURCE) is False


def test_hierarchy_cycles_terminate():
    a = ResourceRef(ResourceType.MISSION, uuid4())
    b = ResourceRef(ResourceType.MISSION, uuid4())
    operator = uuid4()
    policy = _policy(
        [],
        {operator: Profile(level=0)},
        parents={
            (ResourceType.MISSION, a.key()): [b],
            (ResourceType.MISSION, b.key()): [a],
        },
    )
    assert policy.is_allowed(operator, Operation.VIEW, a) is False
