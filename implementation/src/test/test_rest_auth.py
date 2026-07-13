# SPDX-License-Identifier: CC-BY-SA-4.0
"""Autenticazione REST: login locale e isolamento tra app distinte.

``test_two_apps_have_independent_auth`` protegge il blueprint auth dal vecchio
stato globale condiviso: due RestApp diverse devono usare ciascuna il proprio
AuthService, non l'ultimo registrato a livello di modulo.
"""
import asyncio
import uuid

from src.application.services._shared import acl_bypass


def test_local_login_returns_token(rest_app, seed_admin):
    app, svcs = rest_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        r = await client.post(
            "/api/auth/login", json={"username": "admin", "password": "ValidPassword1!"}
        )
        assert r.status_code == 200
        assert (await r.get_json()).get("token")

    asyncio.run(scenario())


def _build_rest(monkeypatch, tmp_path, name):
    db = tmp_path / f"{name}.db"
    for key, value in {
        "MISSIONMANAGER_DATABASE_URL": f"sqlite:///{db}",
        "MISSIONMANAGER_SECRET_KEY": "x" * 40,
        "MISSIONMANAGER_PERSON_BACKEND": "local",
        "MISSIONMANAGER_AUTH_BACKEND": "local",
        "MISSIONMANAGER_REST_DEV_MODE": "true",
    }.items():
        monkeypatch.setenv(key, value)
    from src.bootstrap.rest import create_rest_app

    app, svcs = create_rest_app()
    with acl_bypass():
        person = svcs.person.add(nicknames=[name])
        svcs.person.set_acl_profile(person.id, acl_level=0)
        svcs.auth_service.set_password(uuid.UUID(person.id), "ValidPassword1!")
    return app


async def _login(app, username):
    client = app.test_client()
    r = await client.post(
        "/api/auth/login", json={"username": username, "password": "ValidPassword1!"}
    )
    return r.status_code


def test_two_apps_have_independent_auth(monkeypatch, tmp_path):
    app_alpha = _build_rest(monkeypatch, tmp_path, "alpha")
    app_bravo = _build_rest(monkeypatch, tmp_path, "bravo")

    # ogni app autentica solo l'operatore presente nel proprio database
    assert asyncio.run(_login(app_alpha, "alpha")) == 200
    assert asyncio.run(_login(app_bravo, "bravo")) == 200
    # "alpha" non esiste nel database di bravo: deve fallire (non riusare l'auth di alpha)
    assert asyncio.run(_login(app_bravo, "alpha")) == 401
