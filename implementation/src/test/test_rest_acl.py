# SPDX-License-Identifier: CC-BY-SA-4.0
"""Enforcement ACL al confine REST + endpoint /api/acl (DESIGN §10).

Copre: 401 per l'anonimo negato, 403 per l'autenticato negato, gestione entry
via REST (autoprotetta da MANAGE_ACL), assegnazione profili (MANAGE_PROFILES),
delega per-risorsa al creatore (seeding).
"""
import asyncio
import uuid

from src.application.services._shared import acl_bypass


def _bearer(svcs, username: str, password: str = "ValidPassword1!"):
    _, token = svcs.auth_service.login_local(username, password)
    return {"Authorization": f"Bearer {token}"}


def _seed_person(svcs, nickname, level=None, groups=None, password="ValidPassword1!"):
    with acl_bypass():
        person = svcs.person.add(nicknames=[nickname])
        if level is not None or groups is not None:
            person = svcs.person.set_acl_profile(
                person.id, acl_level=level, acl_groups=groups
            )
        svcs.auth_service.set_password(uuid.UUID(person.id), password)
    return person


def test_anonymous_denied_gets_401_authenticated_denied_gets_403(rest_app, seed_admin):
    app, svcs = rest_app
    seed_admin(svcs)
    _seed_person(svcs, "viewer", level=100)

    async def scenario():
        client = app.test_client()
        # anonimo su risorsa protetta → 401 con WWW-Authenticate
        r = await client.get("/api/missions")
        assert r.status_code == 401
        assert "WWW-Authenticate" in r.headers

        # autenticato al tier lettura: GET ok, mutazione 403
        headers = _bearer(svcs, "viewer")
        assert (await client.get("/api/missions", headers=headers)).status_code == 200
        r = await client.post(
            "/api/missions",
            headers=headers,
            json={"title": "Op", "objectives": [{"description": "O", "activities": [{"title": "A"}]}]},
        )
        assert r.status_code == 403

    asyncio.run(scenario())


def test_identity_mutations_require_admin_tier(rest_app, seed_admin):
    app, svcs = rest_app
    seed_admin(svcs)
    _seed_person(svcs, "manager", level=50)

    async def scenario():
        client = app.test_client()
        headers = _bearer(svcs, "manager")
        r = await client.post(
            "/api/persons", headers=headers, json={"nicknames": ["x"]}
        )
        assert r.status_code == 403

        admin_headers = _bearer(svcs, "admin")
        r = await client.post(
            "/api/persons", headers=admin_headers, json={"nicknames": ["x"]}
        )
        assert r.status_code == 201

    asyncio.run(scenario())


def test_acl_entries_rest_management(rest_app, seed_admin):
    app, svcs = rest_app
    seed_admin(svcs)
    _seed_person(svcs, "manager", level=50)

    async def scenario():
        client = app.test_client()
        admin_headers = _bearer(svcs, "admin")

        # elenco completo (bootstrap) per l'amministratore
        r = await client.get("/api/acl/entries", headers=admin_headers)
        assert r.status_code == 200
        assert len(await r.get_json()) > 0

        # creazione entry: DENY DELETE sotto soglia 60 su MISSION:*
        r = await client.post(
            "/api/acl/entries",
            headers=admin_headers,
            json={
                "resource_type": "MISSION",
                "resource_id": "*",
                "operation": "DELETE",
                "permission": "DENY",
                "level": 60,
            },
        )
        assert r.status_code == 201
        entry = await r.get_json()

        # aggiornamento e cancellazione
        r = await client.patch(
            f"/api/acl/entries/{entry['id']}",
            headers=admin_headers,
            json={"permission": "ALLOW"},
        )
        assert r.status_code == 200
        assert (await r.get_json())["permission"] == "ALLOW"
        r = await client.delete(
            f"/api/acl/entries/{entry['id']}", headers=admin_headers
        )
        assert r.status_code == 204

        # non-admin: autoprotezione MANAGE_ACL → 403; anonimo → 401
        manager_headers = _bearer(svcs, "manager")
        r = await client.get("/api/acl/entries", headers=manager_headers)
        assert r.status_code == 403
        assert (await client.get("/api/acl/entries")).status_code == 401

    asyncio.run(scenario())


def test_person_acl_profile_rest_endpoint(rest_app, seed_admin):
    app, svcs = rest_app
    seed_admin(svcs)
    person = _seed_person(svcs, "target")
    _seed_person(svcs, "manager", level=50)

    async def scenario():
        client = app.test_client()

        # MANAGE_PROFILES è al tier amministrativo: il Gestore non può
        r = await client.put(
            f"/api/persons/{person.id}/acl",
            headers=_bearer(svcs, "manager"),
            json={"acl_level": 0},
        )
        assert r.status_code == 403

        r = await client.put(
            f"/api/persons/{person.id}/acl",
            headers=_bearer(svcs, "admin"),
            json={"acl_level": 50, "acl_groups": ["ops"]},
        )
        assert r.status_code == 200
        body = await r.get_json()
        assert body["acl_level"] == 50 and body["acl_groups"] == ["ops"]

    asyncio.run(scenario())


def test_creator_delegation_via_seeded_manage_acl(rest_app, seed_admin):
    """Il creatore (seeding) gestisce l'ACL della sua missione via REST."""
    app, svcs = rest_app
    seed_admin(svcs)
    creator = _seed_person(svcs, "creator", level=50)
    mission = svcs.mission.create(
        title="Op", desc="",
        objectives=[{"description": "O", "activities": [{"title": "A"}]}],
        operator_id=uuid.UUID(creator.id),
    )

    async def scenario():
        client = app.test_client()
        headers = _bearer(svcs, "creator")

        # elenco entry della propria missione (seeded MANAGE_ACL)
        r = await client.get(
            "/api/acl/entries",
            headers=headers,
            query_string={"resource_type": "MISSION", "resource_id": mission.id},
        )
        assert r.status_code == 200
        assert [e["operation"] for e in await r.get_json()] == ["MANAGE_ACL"]

        # può aggiungere una entry alla propria missione...
        r = await client.post(
            "/api/acl/entries",
            headers=headers,
            json={
                "resource_type": "MISSION",
                "resource_id": mission.id,
                "operation": "VIEW",
                "permission": "ALLOW",
                "group": "viewers",
            },
        )
        assert r.status_code == 201

        # ...ma non alle radici globali
        r = await client.post(
            "/api/acl/entries",
            headers=headers,
            json={
                "resource_type": "MISSION",
                "resource_id": "*",
                "operation": "VIEW",
                "permission": "ALLOW",
                "level": 1,
            },
        )
        assert r.status_code == 403

    asyncio.run(scenario())


def test_own_view_entries_privatize_resource(rest_app, seed_admin):
    """Entry proprie di VIEW su una missione la rendono visibile solo ai match."""
    app, svcs = rest_app
    admin = seed_admin(svcs)
    _seed_person(svcs, "outsider", level=100)
    insider = _seed_person(svcs, "insider", level=100, groups=["team"])

    mission = svcs.mission.create(
        title="Riservata", desc="",
        objectives=[{"description": "O", "activities": [{"title": "A"}]}],
        operator_id=uuid.UUID(admin.id),
    )
    svcs.acl.create_entry(
        "MISSION", mission.id, "VIEW", "ALLOW", group="team",
        operator_id=uuid.UUID(admin.id),
    )

    async def scenario():
        client = app.test_client()
        r = await client.get(
            f"/api/missions/{mission.id}", headers=_bearer(svcs, "insider")
        )
        assert r.status_code == 200
        # le entry proprie esauriscono la decisione: la soglia globale non si applica
        r = await client.get(
            f"/api/missions/{mission.id}", headers=_bearer(svcs, "outsider")
        )
        assert r.status_code == 403

    asyncio.run(scenario())
