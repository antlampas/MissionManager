# SPDX-License-Identifier: CC-BY-SA-4.0
"""Comportamento HTTP della REST API: CRUD, mappatura errori, autenticazione."""
import asyncio
import uuid

from src.frontend.api.middleware import _rate_limited_operation
from src.infrastructure.security.rate_limit import RateLimitedOperation


def _bearer(svcs):
    _, token = svcs.auth_service.login_local("admin", "ValidPassword1!")
    return {"Authorization": f"Bearer {token}"}


def test_mission_crud_happy_path(rest_app, seed_admin):
    app, svcs = rest_app
    seed_admin(svcs)
    headers = _bearer(svcs)

    async def scenario():
        client = app.test_client()
        r = await client.post(
            "/api/missions",
            headers=headers,
            json={"title": "Op", "objectives": [{"description": "O", "activities": [{"title": "A"}]}]},
        )
        assert r.status_code == 201
        mission_id = (await r.get_json())["id"]
        assert (await client.get("/api/missions", headers=headers)).status_code == 200
        # gli obiettivi restano leggibili...
        r = await client.get(f"/api/missions/{mission_id}/objectives", headers=headers)
        assert r.status_code == 200
        assert len(await r.get_json()) == 1
        # ...ma il blueprint è immutabile: l'aggiunta di obiettivi non è consentita
        # (il metodo POST non è registrato per questa route) e non altera il blueprint.
        r = await client.post(
            f"/api/missions/{mission_id}/objectives",
            headers=headers,
            json={"description": "O2", "activities": [{"title": "B"}]},
        )
        assert r.status_code != 201
        r = await client.get(f"/api/missions/{mission_id}/objectives", headers=headers)
        assert len(await r.get_json()) == 1

    asyncio.run(scenario())


def test_invalid_body_returns_400(rest_app, seed_admin):
    app, svcs = rest_app
    seed_admin(svcs)
    headers = _bearer(svcs)

    async def scenario():
        client = app.test_client()
        assert (await client.post("/api/missions", headers=headers)).status_code == 400
        assert (await client.post("/api/badges", headers=headers, json={})).status_code == 400

    asyncio.run(scenario())


def test_unauthenticated_request_returns_401(rest_app, seed_admin):
    app, svcs = rest_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        r = await client.post("/api/missions", json={"title": "x"})
        assert r.status_code == 401

    asyncio.run(scenario())


def test_group_member_crud_happy_path(rest_app, seed_admin):
    app, svcs = rest_app
    seed_admin(svcs)
    headers = _bearer(svcs)

    async def scenario():
        client = app.test_client()
        r = await client.post(
            "/api/persons",
            headers=headers,
            json={"nicknames": ["operator"]},
        )
        assert r.status_code == 201
        person_id = (await r.get_json())["id"]

        r = await client.post(
            "/api/groups",
            headers=headers,
            json={"name": "Ops", "zone_type": "VIRTUAL"},
        )
        assert r.status_code == 201
        group_id = (await r.get_json())["id"]

        r = await client.put(
            f"/api/groups/{group_id}",
            headers=headers,
            json={
                "name": "Ops Nord",
                "zone_type": "GEOGRAPHIC",
                "zone_description": "nord",
            },
        )
        assert r.status_code == 200
        body = await r.get_json()
        assert body["name"] == "Ops Nord"
        assert body["zone_type"] == "GEOGRAPHIC"
        assert body["zone_description"] == "nord"

        r = await client.post(
            f"/api/groups/{group_id}/members",
            headers=headers,
            json={"person_id": person_id},
        )
        assert r.status_code == 204

        r = await client.get(f"/api/groups/{group_id}/members", headers=headers)
        assert r.status_code == 200
        assert [p["id"] for p in await r.get_json()] == [person_id]

        r = await client.delete(
            f"/api/groups/{group_id}/members",
            headers=headers,
            json={"person_id": person_id},
        )
        assert r.status_code == 204

        r = await client.get(f"/api/groups/{group_id}/members", headers=headers)
        assert r.status_code == 200
        assert await r.get_json() == []

    asyncio.run(scenario())


def test_group_member_routes_have_distinct_rate_limit_operations():
    path = "/api/groups/00000000-0000-0000-0000-000000000000/members"
    assert (
        _rate_limited_operation(path, "POST")
        == RateLimitedOperation.ADD_GROUP_MEMBER
    )
    assert (
        _rate_limited_operation(
            "/api/groups/00000000-0000-0000-0000-000000000000", "PUT"
        )
        == RateLimitedOperation.UPDATE_GROUP
    )
    assert (
        _rate_limited_operation(path, "DELETE")
        == RateLimitedOperation.REMOVE_GROUP_MEMBER
    )
