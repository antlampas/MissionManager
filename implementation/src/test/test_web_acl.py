# SPDX-License-Identifier: CC-BY-SA-4.0
"""Enforcement ACL al confine della Web App (DESIGN §10).

Copre: soglie di default (lettura/scrittura/amministrazione), profilo anonimo
(redirect al login sulle pagine, 401 sulle mutazioni), delega per-gruppo via
entry, DENY mirato, autoprotezione della pagina /acl.
"""
import asyncio
import re
import uuid

from src.application.services._shared import acl_bypass


async def _csrf(client, path: str) -> str:
    response = await client.get(path)
    match = re.search(
        r'name="csrf-token" content="([^"]+)"',
        (await response.get_data()).decode(),
    )
    assert match
    return match.group(1)


async def _login_as(client, username: str, password: str = "ValidPassword1!"):
    csrf = await _csrf(client, "/login")
    await client.post(
        "/login",
        form={"username": username, "password": password, "csrf_token": csrf},
    )
    return csrf


def _seed_person(svcs, nickname, level=None, groups=None, password="ValidPassword1!"):
    with acl_bypass():
        person = svcs.person.add(nicknames=[nickname])
        if level is not None or groups is not None:
            person = svcs.person.set_acl_profile(
                person.id, acl_level=level, acl_groups=groups
            )
        svcs.auth_service.set_password(uuid.UUID(person.id), password)
    return person


def test_anonymous_gets_login_redirect_on_pages_and_401_on_mutations(web_app, seed_admin):
    app, svcs = web_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        r = await client.get("/missions")
        assert r.status_code in (302, 303)
        assert "/login" in r.headers["Location"]

        # con il token CSRF valido, l'anonimo su una mutazione riceve 401
        csrf = await _csrf(client, "/login")
        r = await client.post(
            "/missions/new", json={"title": "x"}, headers={"X-CSRF-Token": csrf}
        )
        assert r.status_code == 401

    asyncio.run(scenario())


def test_read_tier_can_view_but_not_mutate(web_app, seed_admin):
    app, svcs = web_app
    seed_admin(svcs)
    _seed_person(svcs, "viewer", level=100)  # soglia di lettura, non di scrittura

    async def scenario():
        client = app.test_client()
        await _login_as(client, "viewer")

        assert (await client.get("/missions")).status_code == 200
        assert (await client.get("/persons")).status_code == 200

        csrf = await _csrf(client, "/missions")
        r = await client.post(
            "/missions/new",
            json={"title": "Op", "objectives": [{"description": "O", "activities": [{"title": "A"}]}]},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 403
        # il form di creazione è mappato sull'operazione: vietato anche in GET
        assert (await client.get("/missions/new")).status_code == 403
        # la pagina di amministrazione ACL è fuori portata
        assert (await client.get("/acl")).status_code == 403

    asyncio.run(scenario())


def test_write_tier_can_mutate_but_not_administer(web_app, seed_admin):
    app, svcs = web_app
    seed_admin(svcs)
    _seed_person(svcs, "manager", level=50)

    async def scenario():
        client = app.test_client()
        await _login_as(client, "manager")
        csrf = await _csrf(client, "/missions")
        headers = {"X-CSRF-Token": csrf}

        r = await client.post(
            "/missions/new",
            json={"title": "Op", "objectives": [{"description": "O", "activities": [{"title": "A"}]}]},
            headers=headers,
        )
        assert r.status_code == 201

        # identità e profili restano al tier amministrativo
        assert (
            await client.post("/persons/new", json={"nicknames": ["x"]}, headers=headers)
        ).status_code == 403
        assert (
            await client.post(
                "/acl/profile", json={"person_id": "x", "acl_level": 0}, headers=headers
            )
        ).status_code == 403

    asyncio.run(scenario())


def test_group_delegation_via_entry(web_app, seed_admin):
    """Una entry ALLOW con criterio di gruppo delega una singola operazione."""
    app, svcs = web_app
    admin = seed_admin(svcs)
    operator = _seed_person(svcs, "runner", groups=["runners"])  # livello anonimo

    mission = svcs.mission.create(
        title="Op", desc="",
        objectives=[{"description": "O", "activities": [{"title": "A"}]}],
        operator_id=uuid.UUID(admin.id),
    )
    assignment = svcs.assignment.create(
        mission_id=mission.id, assignee_type="PERSON", assignee_id=operator.id,
        operator_id=uuid.UUID(admin.id),
    )
    activity_id = assignment.objectives[0].activities[0].id

    # delega: il gruppo "runners" può vedere e avanzare questa attività.
    svcs.acl.create_entry(
        "ACTIVITY", activity_id, "VIEW", "ALLOW", group="runners",
        operator_id=uuid.UUID(admin.id),
    )
    svcs.acl.create_entry(
        "ACTIVITY", activity_id, "ASSIGN", "ALLOW", group="runners",
        operator_id=uuid.UUID(admin.id),
    )
    svcs.acl.create_entry(
        "ACTIVITY", activity_id, "UPDATE_STATUS", "ALLOW", group="runners",
        operator_id=uuid.UUID(admin.id),
    )

    async def scenario():
        client = app.test_client()
        csrf = await _login_as(client, "runner")
        headers = {"X-CSRF-Token": csrf}

        r = await client.post(
            f"/activities/{activity_id}/assign",
            json={"person_id": operator.id},
            headers=headers,
        )
        assert r.status_code == 200
        r = await client.put(
            f"/activities/{activity_id}/status",
            json={"status": "IN_PROGRESS"},
            headers=headers,
        )
        assert r.status_code == 200

        # nessuna delega sulle missioni: la creazione resta vietata
        r = await client.post(
            "/missions/new",
            json={"title": "X", "objectives": [{"description": "O", "activities": [{"title": "A"}]}]},
            headers=headers,
        )
        assert r.status_code == 403

    asyncio.run(scenario())


def test_targeted_deny_overrides_threshold(web_app, seed_admin):
    """DENY > ALLOW: una entry DENY blocca anche chi soddisfa la soglia."""
    app, svcs = web_app
    admin = seed_admin(svcs)
    _seed_person(svcs, "suspended", level=50, groups=["suspended"])

    svcs.acl.create_entry(
        "MISSION", "*", "UPDATE_STATUS", "DENY", group="suspended",
        operator_id=uuid.UUID(admin.id),
    )
    mission = svcs.mission.create(
        title="Op", desc="",
        objectives=[{"description": "O", "activities": [{"title": "A"}]}],
        operator_id=uuid.UUID(admin.id),
    )
    assignment = svcs.assignment.create(
        mission_id=mission.id, assignee_type=None, assignee_id=None,
        operator_id=uuid.UUID(admin.id),
    )

    async def scenario():
        client = app.test_client()
        await _login_as(client, "suspended")
        csrf = await _csrf(client, "/missions")
        headers = {"X-CSRF-Token": csrf}

        # il tier di scrittura consentirebbe, ma il DENY mirato prevale
        r = await client.put(
            f"/assignments/{assignment.id}/status",
            json={"status": "IN_PROGRESS"},
            headers=headers,
        )
        assert r.status_code == 403
        # le altre mutazioni del tier restano permesse
        r = await client.post(
            "/missions/new",
            json={"title": "Y", "objectives": [{"description": "O", "activities": [{"title": "A"}]}]},
            headers=headers,
        )
        assert r.status_code == 201

    asyncio.run(scenario())


def test_admin_can_use_acl_page(web_app, seed_admin):
    app, svcs = web_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        await _login_as(client, "admin")
        assert (await client.get("/acl")).status_code == 200

    asyncio.run(scenario())
