# SPDX-License-Identifier: CC-BY-SA-4.0
"""Nucleo ACL di dominio: invarianti INV-1..INV-5, match, Profile (DESIGN §10)."""
from uuid import uuid4

import pytest

from src.domain.acl import (
    ANON_SENTINEL,
    AclEntry,
    JoinOp,
    Operation,
    Permission,
    Profile,
    ResourceRef,
    SubjectRef,
)
from src.domain.enums import ResourceType
from src.domain.exceptions import ValidationError


def _entry(**overrides):
    defaults = dict(
        id=uuid4(),
        subject=SubjectRef.public(),
        resource=ResourceRef(ResourceType.MISSION, uuid4()),
        operation=Operation.VIEW,
        permission=Permission.ALLOW,
        level=50,
    )
    defaults.update(overrides)
    return AclEntry(**defaults)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def test_profile_always_includes_public_group():
    assert "public" in Profile(level=5).groups
    assert "public" in Profile.anonymous().groups
    assert Profile(level=5, groups=frozenset({"ops"})).stored_groups() == ["ops"]


def test_profile_rejects_negative_level():
    with pytest.raises(ValidationError):
        Profile(level=-1)


def test_anonymous_profile_is_least_privileged():
    assert Profile.anonymous().level == ANON_SENTINEL


# ---------------------------------------------------------------------------
# Invarianti
# ---------------------------------------------------------------------------

def test_inv1_requires_level_or_group():
    with pytest.raises(ValidationError, match="INV-1"):
        _entry(level=None, group=None).validate()
    _entry(level=None, group="ops").validate()   # solo gruppo: ok
    _entry(level=10, group=None).validate()      # solo livello: ok


def test_inv2_mutating_operation_cannot_reach_anonymous():
    # PUBLIC con soglia universale su operazione mutante → matcherebbe l'anonimo
    with pytest.raises(ValidationError, match="INV-2"):
        _entry(operation=Operation.DELETE, level=ANON_SENTINEL).validate()
    # PUBLIC con gruppo universale su mutante → idem
    with pytest.raises(ValidationError, match="INV-2"):
        _entry(operation=Operation.DELETE, level=None, group="public").validate()
    # USER + subject_join=OR + soglia universale → l'anonimo passerebbe dal profilo
    with pytest.raises(ValidationError, match="INV-2"):
        _entry(
            subject=SubjectRef.user(uuid4()),
            operation=Operation.DELETE,
            level=ANON_SENTINEL,
            subject_join=JoinOp.OR,
        ).validate()
    # soglia mutante ordinaria (non raggiungibile dall'anonimo): ok
    _entry(operation=Operation.DELETE, level=50).validate()
    # in sola lettura PUBLIC universale è ammesso (concessioni pubbliche)
    _entry(operation=Operation.VIEW, level=None, group="public").validate()


def test_inv3_rejects_negative_level_and_blank_group():
    with pytest.raises(ValidationError, match="INV-3"):
        _entry(level=-2).validate()
    with pytest.raises(ValidationError, match="INV-1"):
        _entry(level=None, group="   ").validate()


def test_inv5_rejects_public_with_subject_join_or():
    with pytest.raises(ValidationError, match="INV-5"):
        _entry(subject_join=JoinOp.OR).validate()


# ---------------------------------------------------------------------------
# Match (§5.1)
# ---------------------------------------------------------------------------

def test_match_public_level_threshold():
    entry = _entry(level=50)
    assert entry.matches(uuid4(), Profile(level=50)) is True
    assert entry.matches(uuid4(), Profile(level=10)) is True   # più privilegiato
    assert entry.matches(uuid4(), Profile(level=51)) is False
    assert entry.matches(None, Profile.anonymous()) is False


def test_match_group_membership():
    entry = _entry(level=None, group="ops")
    assert entry.matches(uuid4(), Profile(level=100, groups=frozenset({"ops"}))) is True
    assert entry.matches(uuid4(), Profile(level=0)) is False


def test_match_profile_join_or_and():
    profile = Profile(level=80, groups=frozenset({"ops"}))
    either = _entry(level=50, group="ops", profile_join=JoinOp.OR)
    both = _entry(level=50, group="ops", profile_join=JoinOp.AND)
    assert either.matches(uuid4(), profile) is True     # gruppo basta
    assert both.matches(uuid4(), profile) is False      # livello 80 > 50


def test_match_user_subject_and_join():
    alice = uuid4()
    entry = _entry(subject=SubjectRef.user(alice), level=50)
    assert entry.matches(alice, Profile(level=10)) is True
    assert entry.matches(alice, Profile(level=99)) is False   # AND: livello insufficiente
    assert entry.matches(uuid4(), Profile(level=10)) is False  # altro soggetto


def test_match_user_subject_or_join():
    alice = uuid4()
    entry = _entry(
        subject=SubjectRef.user(alice), level=50, subject_join=JoinOp.OR
    )
    assert entry.matches(alice, Profile(level=99)) is True     # è Alice
    assert entry.matches(uuid4(), Profile(level=10)) is True   # oppure livello <= 50
    assert entry.matches(uuid4(), Profile(level=99)) is False


def test_subject_ref_validation():
    with pytest.raises(ValidationError):
        SubjectRef(type=SubjectRef.public().type, id="x")  # PUBLIC con id
    with pytest.raises(ValidationError):
        SubjectRef.user("")
