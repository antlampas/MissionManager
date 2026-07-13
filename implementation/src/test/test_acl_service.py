# SPDX-License-Identifier: CC-BY-SA-4.0
"""AclService: bootstrap, seeding automatico, gestione entry autoprotetta.

Usa il sistema reale (bootstrap su SQLite) per verificare l'integrazione con
persistenza, gerarchia e soglie di default.
"""
import uuid

import pytest

from src.application.services._shared import acl_bypass
from src.domain.acl import Operation, ResourceRef, SYSTEM_RESOURCE
from src.domain.enums import ResourceType
from src.domain.exceptions import ForbiddenError, NotFoundError, ValidationError


def _mission(svcs, operator_id):
    return svcs.mission.create(
        title="Op",
        desc="",
        objectives=[{"description": "O", "activities": [{"title": "A"}]}],
        operator_id=operator_id,
    )


# ---------------------------------------------------------------------------
# Bootstrap: soglie di default seminate una sola volta
# ---------------------------------------------------------------------------

def test_bootstrap_seeds_default_entries_once(web_app):
    _, svcs = web_app
    with svcs.uow.transaction():
        entries = svcs.acl_entry_repo.list_all()
    assert entries, "il bootstrap deve seminare le entry di default"

    # idempotente: un secondo ensure non duplica
    count = len(entries)
    svcs.acl.ensure_bootstrap_entries(100, 50, 0)
    with svcs.uow.transaction():
        assert len(svcs.acl_entry_repo.list_all()) == count

        # le soglie chiave esistono
        system_ops = {
            e.operation
            for e in svcs.acl_entry_repo.list_by_resource(SYSTEM_RESOURCE)
        }
        assert Operation.CREATE_MISSION in system_ops
        assert Operation.MANAGE_ACL in system_ops
        assert Operation.MANAGE_PROFILES in system_ops

        mission_root_ops = {
            e.operation
            for e in svcs.acl_entry_repo.list_by_resource(
                ResourceRef.type_root(ResourceType.MISSION)
            )
        }
        group_root_ops = {
            e.operation
            for e in svcs.acl_entry_repo.list_by_resource(
                ResourceRef.type_root(ResourceType.GROUP)
            )
        }
    assert {Operation.VIEW, Operation.LIST, Operation.DELETE} <= mission_root_ops
    assert Operation.EDIT in group_root_ops


# ---------------------------------------------------------------------------
# Seeding automatico (D7): il creatore riceve MANAGE_ACL sulla risorsa
# ---------------------------------------------------------------------------

def test_resource_creation_seeds_manage_acl_for_creator(web_app, seed_admin):
    _, svcs = web_app
    admin = seed_admin(svcs)
    mission = _mission(svcs, uuid.UUID(admin.id))

    resource = ResourceRef(ResourceType.MISSION, uuid.UUID(mission.id))
    with svcs.uow.transaction():
        seeded = svcs.acl_entry_repo.list_by_resource(resource)
    assert [e.operation for e in seeded] == [Operation.MANAGE_ACL]
    assert seeded[0].subject.id == admin.id
    # la entry seminata usa la soglia universale («il creatore, incondizionatamente»)
    assert seeded[0].level == 2**31 - 1

    # l'eliminazione della risorsa elimina in cascata le sue entry
    svcs.mission.delete(mission.id, operator_id=uuid.UUID(admin.id))
    with svcs.uow.transaction():
        assert svcs.acl_entry_repo.list_by_resource(resource) == []


# ---------------------------------------------------------------------------
# Gestione entry: validazione e autoprotezione MANAGE_ACL
# ---------------------------------------------------------------------------

def test_create_entry_validates_invariants(web_app, seed_admin):
    _, svcs = web_app
    admin = seed_admin(svcs)
    operator = uuid.UUID(admin.id)

    public_read = svcs.acl.create_entry(
        "MISSION", "*", "VIEW", "ALLOW", operator_id=operator
    )
    assert public_read.group == "public"
    svcs.acl.delete_entry(public_read.id, operator_id=operator)
    with pytest.raises(ValidationError):  # operazione sconosciuta
        svcs.acl.create_entry(
            "MISSION", "*", "FLY", "ALLOW", level=1, operator_id=operator
        )
    with pytest.raises(ValidationError):  # tipo risorsa sconosciuto
        svcs.acl.create_entry(
            "WORMHOLE", "*", "VIEW", "ALLOW", level=1, operator_id=operator
        )

    dto = svcs.acl.create_entry(
        "MISSION", "*", "VIEW", "ALLOW", group="viewers", operator_id=operator
    )
    assert dto.operation == "VIEW" and dto.group == "viewers"

    updated = svcs.acl.update_entry(dto.id, permission="DENY", operator_id=operator)
    assert updated.permission == "DENY"

    svcs.acl.delete_entry(dto.id, operator_id=operator)
    with pytest.raises(NotFoundError):
        svcs.acl.delete_entry(dto.id, operator_id=operator)


def test_entry_management_requires_manage_acl(web_app, seed_admin):
    _, svcs = web_app
    seed_admin(svcs)
    with acl_bypass():
        low = svcs.person.add(nicknames=["low"])  # profilo meno privilegiato

    with pytest.raises(ForbiddenError):
        svcs.acl.list_all_entries(operator_id=uuid.UUID(low.id))
    with pytest.raises(ForbiddenError):
        svcs.acl.create_entry(
            "MISSION", "*", "VIEW", "ALLOW", level=1,
            operator_id=uuid.UUID(low.id),
        )
    with pytest.raises(ForbiddenError):
        svcs.acl.list_all_entries(operator_id=None)  # anonimo


def test_seeded_creator_can_manage_only_his_resource(web_app, seed_admin):
    """Il seeding sostituisce l'ownership: controllo esplicito e revocabile."""
    _, svcs = web_app
    admin = seed_admin(svcs)
    with acl_bypass():
        creator = svcs.person.add(nicknames=["creator"])
        svcs.person.set_acl_profile(creator.id, acl_level=50)  # tier scrittura

    mission = _mission(svcs, uuid.UUID(creator.id))

    # il creatore gestisce le entry della propria missione...
    entry = svcs.acl.create_entry(
        "MISSION", mission.id, "VIEW", "ALLOW", group="viewers",
        operator_id=uuid.UUID(creator.id),
    )
    assert entry.resource_id == mission.id
    # ...ma non quelle globali (MANAGE_ACL su SYSTEM richiede il tier admin)
    with pytest.raises(ForbiddenError):
        svcs.acl.create_entry(
            "MISSION", "*", "VIEW", "ALLOW", level=1,
            operator_id=uuid.UUID(creator.id),
        )

    # l'amministratore può revocare la entry seminata del creatore
    with svcs.uow.transaction():
        seeded = [
            e for e in svcs.acl_entry_repo.list_by_resource(
                ResourceRef(ResourceType.MISSION, uuid.UUID(mission.id))
            )
            if e.operation == Operation.MANAGE_ACL
        ]
    svcs.acl.delete_entry(str(seeded[0].id), operator_id=uuid.UUID(admin.id))
    with pytest.raises(ForbiddenError):
        svcs.acl.create_entry(
            "MISSION", mission.id, "VIEW", "DENY", group="x",
            operator_id=uuid.UUID(creator.id),
        )


def test_seeding_can_be_disabled(monkeypatch, tmp_path, seed_admin):
    monkeypatch.setenv("MISSIONMANAGER_DATABASE_URL", f"sqlite:///{tmp_path/'mm.db'}")
    monkeypatch.setenv("MISSIONMANAGER_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("MISSIONMANAGER_PERSON_BACKEND", "local")
    monkeypatch.setenv("MISSIONMANAGER_AUTH_BACKEND", "local")
    monkeypatch.setenv("MISSIONMANAGER_WEB_SECURE_COOKIES", "false")
    monkeypatch.setenv("MISSIONMANAGER_ACL_SEEDING_ENABLED", "false")
    from src.bootstrap.web import create_web_app

    _, svcs = create_web_app()
    admin = seed_admin(svcs)
    mission = _mission(svcs, uuid.UUID(admin.id))
    resource = ResourceRef(ResourceType.MISSION, uuid.UUID(mission.id))
    with svcs.uow.transaction():
        assert svcs.acl_entry_repo.list_by_resource(resource) == []
