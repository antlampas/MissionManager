# SPDX-License-Identifier: CC-BY-SA-4.0
"""Cambio password REST: self-service vs amministratore.

Il controllo vive al confine (router auth) ma passa per
``AuthorizationPolicy.is_allowed`` (operazione ``EDIT`` sulla risorsa PERSON,
DESIGN §10), non leggendo il profilo direttamente. Ogni operatore può cambiare
la propria password; cambiare quella di un altro richiede EDIT sulla sua
risorsa (di default, il tier amministrativo di bootstrap).
"""
import asyncio


def _bearer(svcs, username: str):
    _, token = svcs.auth_service.login_local(username, "ValidPassword1!")
    return {"Authorization": f"Bearer {token}"}


def test_password_self_service_and_admin_rule(rest_app, seed_admin):
    app, svcs = rest_app
    admin = seed_admin(svcs, nickname="admin", acl_level=0)
    manager = seed_admin(svcs, nickname="manager", acl_level=50)

    async def scenario():
        client = app.test_client()

        # Operatore non-admin (livello 50 > admin_threshold 0): NON può cambiare
        # la password di un altro operatore (EDIT su PERSON:* richiede <= 0).
        r = await client.put(
            "/api/auth/password",
            headers=_bearer(svcs, "manager"),
            json={"person_id": admin.id, "password": "HackedByManager1!"},
        )
        assert r.status_code == 403

        # Ma può cambiare la PROPRIA password (self-service).
        r = await client.put(
            "/api/auth/password",
            headers=_bearer(svcs, "manager"),
            json={"person_id": manager.id, "password": "ManagerNewPass1!"},
        )
        assert r.status_code == 200

        # L'amministratore (livello 0 <= soglia 0) può cambiare la password altrui.
        r = await client.put(
            "/api/auth/password",
            headers=_bearer(svcs, "admin"),
            json={"person_id": manager.id, "password": "ResetByAdmin1!"},
        )
        assert r.status_code == 200

    asyncio.run(scenario())
