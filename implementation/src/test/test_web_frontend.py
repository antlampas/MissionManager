# SPDX-License-Identifier: CC-BY-SA-4.0
"""Comportamento HTTP della Web App: setup, asset statici, flussi di creazione."""
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
        r'name="csrf_token" value="([^"]+)"|name="csrf-token" content="([^"]+)"',
        (await response.get_data()).decode(),
    )
    assert match
    return match.group(1) or match.group(2)


async def _login(client):
    csrf = await _csrf(client, "/login")
    return await client.post(
        "/login",
        form={"username": "admin", "password": "ValidPassword1!", "csrf_token": csrf},
    )


def test_setup_rejects_short_password_without_orphan(web_app):
    app, svcs = web_app

    async def scenario():
        client = app.test_client()
        csrf = await _csrf(client, "/setup")
        # password sotto policy: rifiutata, e nessun utente "orfano" deve restare
        r = await client.post(
            "/setup", form={"username": "admin", "password": "short", "password2": "short", "csrf_token": csrf}
        )
        assert r.status_code == 400
        assert _setup(svcs.person.list, {}) == []
        # input valido: amministratore creato, redirect al login
        r = await client.post(
                "/setup",
                form={"username": "admin", "password": "ValidPassword1!", "password2": "ValidPassword1!", "csrf_token": csrf},
        )
        assert r.status_code in (302, 303)
        assert len(_setup(svcs.person.list, {})) == 1

    asyncio.run(scenario())


def test_static_assets_are_served(web_app, seed_admin):
    app, svcs = web_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        await _login(client)
        r = await client.get("/static/app.js")
        assert r.status_code == 200
        assert "mission-create" in (await r.get_data()).decode()
        assert (await client.get("/static/style.css")).status_code == 200

    asyncio.run(scenario())


def test_dark_theme_keeps_shared_javascript_and_serves_its_css(tmp_path, monkeypatch):
    monkeypatch.setenv("MISSIONMANAGER_DATABASE_URL", f"sqlite:///{tmp_path / 'dark.db'}")
    monkeypatch.setenv("MISSIONMANAGER_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("MISSIONMANAGER_WEB_THEME", "dark")
    monkeypatch.setenv("MISSIONMANAGER_WEB_SECURE_COOKIES", "false")
    from src.bootstrap.web import create_web_app

    app, _ = create_web_app()

    async def scenario():
        client = app.test_client()
        assert (await client.get("/static/app.js")).status_code == 200
        css = await client.get("/static/theme.css")
        assert css.status_code == 200
        assert "dark" in (await css.get_data()).decode().lower()

    asyncio.run(scenario())


def test_create_mission_flow_and_listing(web_app, seed_admin):
    app, svcs = web_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        await _login(client)
        csrf = await _csrf(client, "/missions")
        r = await client.post(
            "/missions/new",
            json={
                "title": "Operazione Alba",
                "description": "d",
                "objectives": [{"description": "O", "activities": [{"title": "A"}]}],
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 201
        # la missione compare nella lista
        r = await client.get("/missions")
        assert "Operazione Alba" in (await r.get_data()).decode()

    asyncio.run(scenario())


def test_create_mission_invalid_input_returns_400(web_app, seed_admin):
    app, svcs = web_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        await _login(client)
        csrf = await _csrf(client, "/missions")
        mission = _setup(
            svcs.mission.create,
            title="Op",
            desc="",
            objectives=[{"description": "O", "activities": [{"title": "A"}]}],
            operator_id=uuid.uuid4(),
        )
        # nessun body, titolo mancante, obiettivo senza attività: tutti 400 (non 415/500)
        headers = {"X-CSRF-Token": csrf}
        assert (await client.post("/missions/new", headers=headers)).status_code == 400
        assert (await client.post("/missions/new", json={"objectives": []}, headers=headers)).status_code == 400
        # blueprint immutabile: la route di aggiunta obiettivi non esiste più (404)
        r = await client.post(f"/missions/{mission.id}/objectives", json={}, headers=headers)
        assert r.status_code == 404

    asyncio.run(scenario())


def test_web_mutations_require_csrf_token(web_app, seed_admin):
    app, svcs = web_app
    seed_admin(svcs)

    async def scenario():
        client = app.test_client()
        await client.get("/login")  # inizializza la sessione e il token
        rejected = await client.post(
            "/login", form={"username": "admin", "password": "ValidPassword1!"}
        )
        assert rejected.status_code == 400
        assert "CSRF" in (await rejected.get_data()).decode()
        assert (await _login(client)).status_code in (302, 303)

    asyncio.run(scenario())


def _secure_cookie_flag(monkeypatch, tmp_path, *, secure_cookies=None, rest_dev_mode=None) -> bool:
    monkeypatch.setenv("MISSIONMANAGER_DATABASE_URL", f"sqlite:///{tmp_path / 'cookie.db'}")
    monkeypatch.setenv("MISSIONMANAGER_SECRET_KEY", "x" * 40)
    if secure_cookies is None:
        monkeypatch.delenv("MISSIONMANAGER_WEB_SECURE_COOKIES", raising=False)
    else:
        monkeypatch.setenv(
            "MISSIONMANAGER_WEB_SECURE_COOKIES", "true" if secure_cookies else "false"
        )
    if rest_dev_mode is not None:
        monkeypatch.setenv("MISSIONMANAGER_REST_DEV_MODE", "true" if rest_dev_mode else "false")
    from src.bootstrap.web import create_web_app

    app, _ = create_web_app()
    return app.config["SESSION_COOKIE_SECURE"]


def test_session_cookie_secure_defaults_to_true(tmp_path, monkeypatch):
    """Sicuro per default (produzione dietro TLS)."""
    from src.config import WebConfigLoader

    monkeypatch.delenv("MISSIONMANAGER_WEB_SECURE_COOKIES", raising=False)
    assert WebConfigLoader.load().secure_cookies is True
    assert _secure_cookie_flag(monkeypatch, tmp_path) is True


def test_session_cookie_secure_can_be_disabled_for_http_dev(tmp_path, monkeypatch):
    """Dev locale su HTTP: il cookie non dev'essere Secure, o il browser lo scarta."""
    assert _secure_cookie_flag(monkeypatch, tmp_path, secure_cookies=False) is False


def test_session_cookie_secure_decoupled_from_rest_dev_mode(tmp_path, monkeypatch):
    """rest_dev_mode è auth REST e non deve più influenzare il cookie Web."""
    assert _secure_cookie_flag(monkeypatch, tmp_path, rest_dev_mode=True) is True
