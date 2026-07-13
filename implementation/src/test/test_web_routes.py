# SPDX-License-Identifier: CC-BY-SA-4.0
"""Copertura delle rotte Web aggiunte: persone, gruppi, badge e azioni di
dettaglio (assegnazione, cambio stato, badge) sulla Web App default."""
import asyncio
import re
import uuid

from src.application.services._shared import acl_bypass


def _setup(callable_, *args, **kwargs):
    with acl_bypass():
        return callable_(*args, **kwargs)


async def _csrf(client, path: str) -> str:
    response = await client.get(path)
    match = re.search(
        r'name="csrf-token" content="([^"]+)"',
        (await response.get_data()).decode(),
    )
    assert match
    return match.group(1)


async def _login(client):
    csrf = await _csrf(client, "/login")
    return await client.post(
        "/login",
        form={"username": "admin", "password": "ValidPassword1!", "csrf_token": csrf},
    )


def test_navigation_pages_render(web_app, seed_admin):
    app, svcs = web_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        await _login(client)
        for path in (
            "/assignments", "/assignments/new",
            "/persons", "/persons/new",
            "/groups", "/groups/new",
            "/acl",
            "/badges", "/badges/new",
        ):
            r = await client.get(path)
            assert r.status_code == 200, (path, r.status_code)
        # i link di navigazione compaiono nell'header
        body = (await (await client.get("/missions")).get_data()).decode()
        assert "/assignments" in body
        assert "/persons" in body and "/groups" in body and "/badges" in body
        assert "/acl" in body and ">ACL<" in body.replace("\n", "").replace(" ", "")
        # gli asset statici sono versionati (cache-busting): senza ?v=<mtime> il
        # browser servirebbe un app.js obsoleto dalla cache (max-age lungo).
        assert re.search(r"/static/app\.js\?v=\d+", body)
        assert re.search(r"/static/theme\.css\?v=\d+", body)

    asyncio.run(scenario())


def test_person_crud_flow(web_app, seed_admin):
    app, svcs = web_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        await _login(client)
        csrf = await _csrf(client, "/persons")
        headers = {"X-CSRF-Token": csrf}

        r = await client.post(
            "/persons/new", json={"nicknames": ["bravo"]}, headers=headers
        )
        assert r.status_code == 201
        pid = (await r.get_json())["id"]

        assert (await client.get(f"/persons/{pid}")).status_code == 200

        r = await client.put(
            f"/persons/{pid}",
            json={"nicknames": ["bravo", "b2"]},
            headers=headers,
        )
        assert r.status_code == 200
        assert "b2" in _setup(svcs.person.get, pid).nicknames

        assert (await client.delete(f"/persons/{pid}", headers=headers)).status_code == 204
        # bravo eliminato; resta solo l'admin seminato
        assert pid not in {p.id for p in _setup(svcs.person.list, {})}

    asyncio.run(scenario())


def test_group_and_members_flow(web_app, seed_admin):
    app, svcs = web_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        await _login(client)
        csrf = await _csrf(client, "/groups")
        headers = {"X-CSRF-Token": csrf}

        person = _setup(svcs.person.add, nicknames=["charlie"])

        r = await client.post(
            "/groups/new",
            json={"name": "Alpha", "zone_type": "GEOGRAPHIC", "zone_description": "nord"},
            headers=headers,
        )
        assert r.status_code == 201
        gid = (await r.get_json())["id"]

        # l'elenco gruppi mostra nome, tipo zona e descrizione zona
        listing = (await (await client.get("/groups")).get_data()).decode()
        assert "Alpha" in listing
        assert "GEOGRAPHIC" in listing
        assert "nord" in listing

        assert (await client.get(f"/groups/{gid}")).status_code == 200

        r = await client.put(
            f"/groups/{gid}",
            json={
                "name": "Alpha Nord",
                "zone_type": "VIRTUAL",
                "zone_description": "canale ops",
            },
            headers=headers,
        )
        assert r.status_code == 200
        assert (await r.get_json())["name"] == "Alpha Nord"
        updated = _setup(svcs.person.get_group, gid)
        assert updated.zone_type == "VIRTUAL"
        assert updated.zone_description == "canale ops"

        detail = (await (await client.get(f"/groups/{gid}")).get_data()).decode()
        assert "Alpha Nord" in detail and "Salva modifiche" in detail

        r = await client.post(
            f"/groups/{gid}/members", json={"person_id": person.id}, headers=headers
        )
        assert r.status_code == 204
        assert [p.id for p in _setup(svcs.person.list_by_group, gid)] == [person.id]

        r = await client.delete(
            f"/groups/{gid}/members", json={"person_id": person.id}, headers=headers
        )
        assert r.status_code == 204
        assert _setup(svcs.person.list_by_group, gid) == []

        assert (await client.delete(f"/groups/{gid}", headers=headers)).status_code == 204

    asyncio.run(scenario())


def test_acl_profile_assignment(web_app, seed_admin):
    """Pagina ACL: assegnazione del profilo (livello e gruppi) di una persona."""
    app, svcs = web_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        await _login(client)
        csrf = await _csrf(client, "/acl")
        headers = {"X-CSRF-Token": csrf}

        p = _setup(svcs.person.add, nicknames=["foxtrot"])

        body = (await (await client.get("/acl")).get_data()).decode()
        assert "Profili" in body and "Regole (entry)" in body

        # assegna livello e gruppi (i gruppi possono arrivare come stringa CSV)
        r = await client.post(
            "/acl/profile",
            json={"person_id": p.id, "acl_level": 50, "acl_groups": "operators, editors"},
            headers=headers,
        )
        assert r.status_code == 200
        dto = _setup(svcs.person.get, p.id)
        assert dto.acl_level == 50
        assert dto.acl_groups == ["editors", "operators"]

        listing = (await (await client.get("/acl")).get_data()).decode()
        assert "operators" in listing and "foxtrot" in listing

        # rimozione da un singolo gruppo
        r = await client.delete(
            "/acl/profile/groups",
            json={"person_id": p.id, "group": "editors"},
            headers=headers,
        )
        assert r.status_code == 200
        assert _setup(svcs.person.get, p.id).acl_groups == ["operators"]

        # livello negativo → 400 (validato dal dominio)
        r = await client.post(
            "/acl/profile",
            json={"person_id": p.id, "acl_level": -1},
            headers=headers,
        )
        assert r.status_code == 400

        # nessun campo → 400
        r = await client.post(
            "/acl/profile", json={"person_id": p.id}, headers=headers
        )
        assert r.status_code == 400

    asyncio.run(scenario())


def test_acl_entry_management(web_app, seed_admin):
    """Pagina ACL: creazione ed eliminazione delle entry."""
    app, svcs = web_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        await _login(client)
        csrf = await _csrf(client, "/acl")
        headers = {"X-CSRF-Token": csrf}

        # entry-soglia: DENY DELETE su MISSION:* a chiunque abbia livello <= 60
        r = await client.post(
            "/acl/entries",
            json={
                "resource_type": "MISSION",
                "resource_id": "*",
                "operation": "DELETE",
                "permission": "DENY",
                "level": 60,
            },
            headers=headers,
        )
        assert r.status_code == 201
        entry_id = (await r.get_json())["id"]

        listing = (await (await client.get("/acl")).get_data()).decode()
        assert "DENY" in listing and entry_id in listing

        # Il service ACL esterno completa le letture pubbliche senza criteri
        # espliciti assegnando il gruppo universale "public".
        r = await client.post(
            "/acl/entries",
            json={
                "resource_type": "MISSION",
                "resource_id": "*",
                "operation": "VIEW",
                "permission": "ALLOW",
            },
            headers=headers,
        )
        assert r.status_code == 201
        assert (await r.get_json())["group"] == "public"

        r = await client.delete(f"/acl/entries/{entry_id}", headers=headers)
        assert r.status_code == 204

    asyncio.run(scenario())


def test_badge_create_and_detail(web_app, seed_admin):
    app, svcs = web_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        await _login(client)
        csrf = await _csrf(client, "/badges")
        headers = {"X-CSRF-Token": csrf}

        # image_url non valido → 400 leggibile (non 500)
        r = await client.post(
            "/badges/new", json={"name": "X", "image_url": "ftp://x"}, headers=headers
        )
        assert r.status_code == 400

        r = await client.post(
            "/badges/new", json={"name": "Hero", "description": "d"}, headers=headers
        )
        assert r.status_code == 201
        bid = (await r.get_json())["id"]
        assert (await client.get(f"/badges/{bid}")).status_code == 200

    asyncio.run(scenario())


def test_assignment_and_activity_actions(web_app, seed_admin):
    app, svcs = web_app
    admin = seed_admin(svcs)
    op = uuid.UUID(admin.id)

    async def scenario():
        client = app.test_client()
        await _login(client)
        csrf = await _csrf(client, "/missions")
        headers = {"X-CSRF-Token": csrf}

        person = _setup(svcs.person.add, nicknames=["delta"])
        mission = svcs.mission.create(
            title="Op",
            desc="",
            objectives=[{"description": "O", "activities": [{"title": "A"}]}],
            operator_id=op,
        )
        badge = svcs.badge.create(name="Done", desc="", operator_id=op)
        assignment = svcs.assignment.create(
            mission_id=mission.id, assignee_type=None, assignee_id=None, operator_id=op
        )

        # la pagina dedicata alle assegnazioni mostra missione assegnata + esecuzione
        body = (await (await client.get("/assignments")).get_data()).decode()
        assert assignment.id in body and mission.title in body
        # la pagina di modifica missione NON contiene più l'assegnazione
        mission_body = (await (await client.get(f"/missions/{mission.id}")).get_data()).decode()
        assert assignment.id not in mission_body

        # assegna l'assignment non assegnato a una persona
        r = await client.post(
            f"/assignments/{assignment.id}/assign",
            json={"assignee_type": "PERSON", "assignee_id": person.id},
            headers=headers,
        )
        assert r.status_code == 200

        act_id = _setup(svcs.assignment.get, assignment.id).objectives[0].activities[0].id

        # il dettaglio assignment offre l'assegnazione inline dell'attività
        detail = (await (await client.get(f"/assignments/{assignment.id}")).get_data()).decode()
        assert f"/activities/{act_id}/assign" in detail

        # assegna persona all'attività (dal dettaglio assignment) e avanza fino a COMPLETED
        assert (await client.post(
            f"/activities/{act_id}/assign", json={"person_id": person.id}, headers=headers
        )).status_code == 200
        assert (await client.put(
            f"/activities/{act_id}/status", json={"status": "IN_PROGRESS"}, headers=headers
        )).status_code == 200
        assert (await client.put(
            f"/activities/{act_id}/status", json={"status": "COMPLETED"}, headers=headers
        )).status_code == 200

        # con tutte le attività COMPLETED, completo l'assignment via la route web
        assert (await client.put(
            f"/assignments/{assignment.id}/status", json={"status": "COMPLETED"}, headers=headers
        )).status_code == 200
        assert _setup(svcs.assignment.get, assignment.id).status == "COMPLETED"
        r = await client.post(
            f"/assignments/{assignment.id}/badge", json={"badge_id": badge.id}, headers=headers
        )
        assert r.status_code == 201

        # le pagine di dettaglio renderizzano con tutte le azioni
        assert (await client.get(f"/activities/{act_id}")).status_code == 200
        assert (await client.get(f"/assignments/{assignment.id}")).status_code == 200

    asyncio.run(scenario())


def test_mission_delete(web_app, seed_admin):
    app, svcs = web_app
    admin = seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        await _login(client)
        csrf = await _csrf(client, "/missions")
        headers = {"X-CSRF-Token": csrf}

        mission = svcs.mission.create(
            title="ToDelete",
            desc="",
            objectives=[{"description": "O", "activities": [{"title": "A"}]}],
            operator_id=uuid.UUID(admin.id),
        )
        r = await client.delete(f"/missions/{mission.id}", headers=headers)
        assert r.status_code == 204
        assert _setup(svcs.mission.list, {}) == []

    asyncio.run(scenario())


def test_dedicated_assignment_creation(web_app, seed_admin):
    """La pagina dedicata crea assegnazioni via POST /assignments (con mission_id)."""
    app, svcs = web_app
    admin = seed_admin(svcs)
    op = uuid.UUID(admin.id)

    async def scenario():
        client = app.test_client()
        await _login(client)
        csrf = await _csrf(client, "/assignments")
        headers = {"X-CSRF-Token": csrf}

        person = _setup(svcs.person.add, nicknames=["echo"])
        mission = svcs.mission.create(
            title="Recon",
            desc="",
            objectives=[{"description": "O", "activities": [{"title": "A"}]}],
            operator_id=op,
        )

        # mission_id mancante → errore di campo obbligatorio, non un 500
        r = await client.post("/assignments", json={}, headers=headers)
        assert r.status_code == 400

        # creazione con assegnatario persona dalla pagina dedicata
        r = await client.post(
            "/assignments",
            json={
                "mission_id": mission.id,
                "assignee_type": "PERSON",
                "assignee_id": person.id,
            },
            headers=headers,
        )
        assert r.status_code == 201
        assignment_id = (await r.get_json())["id"]

        # compare nell'elenco delle missioni assegnate
        listing = (await (await client.get("/assignments")).get_data()).decode()
        assert assignment_id in listing and "Recon" in listing

        # il form di creazione preseleziona la missione passata via querystring
        form_body = (
            await (await client.get(f"/assignments/new?mission={mission.id}")).get_data()
        ).decode()
        assert f'value="{mission.id}" selected' in form_body

    asyncio.run(scenario())
