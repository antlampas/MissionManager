# SPDX-License-Identifier: CC-BY-SA-4.0
"""Invarianti applicative per persone e nickname."""

import pytest

from src.application.services._shared import acl_bypass
from src.domain.exceptions import ValidationError


def test_person_nicknames_are_normalized(web_app):
    _, svcs = web_app

    with acl_bypass():
        person = svcs.person.add(["  Alpha  ", "", " Bravo "])

    assert person.nicknames == ["Alpha", "Bravo"]
    assert person.primary_nickname == "Alpha"

    with acl_bypass():
        updated = svcs.person.update(person.id, nicknames=["", "  Charlie  "])
    assert updated.nicknames == ["Charlie"]
    assert updated.primary_nickname == "Charlie"


def test_person_requires_non_blank_nickname(web_app):
    _, svcs = web_app

    with pytest.raises(ValidationError, match="nickname"):
        with acl_bypass():
            svcs.person.add([" ", ""])


def test_person_acl_profile_assignment(web_app):
    _, svcs = web_app

    with acl_bypass():
        person = svcs.person.add(["Alpha"])
    # profilo di default: livello meno privilegiato, nessun gruppo esplicito
    assert person.acl_level == 2**31 - 1
    assert person.acl_groups == []

    with acl_bypass():
        updated = svcs.person.set_acl_profile(
            person.id, acl_level=50, acl_groups=["operators", "editors"]
        )
    assert updated.acl_level == 50
    assert updated.acl_groups == ["editors", "operators"]

    # rimozione di un singolo gruppo
    with acl_bypass():
        updated = svcs.person.remove_acl_group(person.id, "editors")
    assert updated.acl_groups == ["operators"]


def test_group_name_defaults_to_virtual_zone_and_can_be_updated(web_app):
    _, svcs = web_app

    with acl_bypass():
        group = svcs.person.add_group(name="Ops")
    assert group.name == "Ops"
    assert group.zone_type == "VIRTUAL"

    with acl_bypass():
        updated = svcs.person.update_group(
            group.id,
            name="Ops Nord",
            zone_type="GEOGRAPHIC",
            zone_description="nord",
        )
    assert updated.name == "Ops Nord"
    assert updated.zone_type == "GEOGRAPHIC"
    assert updated.zone_description == "nord"
