# SPDX-License-Identifier: CC-BY-SA-4.0
"""Router REST per autenticazione: login locale, logout, flusso OIDC.

Endpoints esposti sotto /api/auth/:
  POST /api/auth/login             autenticazione locale (username + password)
  POST /api/auth/logout            revoca del token corrente
  GET  /api/auth/oidc/url          ottieni URL di autorizzazione OIDC (SPA stateless)
  POST /api/auth/oidc/callback     completa il flusso OIDC lato REST
  PUT  /api/auth/password          imposta/aggiorna la password locale
"""
from __future__ import annotations

from uuid import UUID

from quart import Blueprint, g, jsonify, request

from ....domain.acl import Operation, ResourceRef
from ....domain.enums import ResourceType
from ....domain.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ValidationError,
)
from ....application.authorization import AuthorizationPolicy
from ....application.services.auth_service import AuthService
from ..._http import parse_json_body, run_blocking


def register_auth_routes(
    auth_service: AuthService,
    auth_policy: AuthorizationPolicy,
) -> Blueprint:
    """Crea e restituisce il blueprint auth legato all'``auth_service`` fornito.

    Blueprint e route sono costruiti localmente (closure su ``auth_service``):
    nessuno stato globale di modulo, così istanze RestApp distinte restano
    indipendenti l'una dall'altra.

    ``auth_policy`` serve al solo endpoint ``PUT /password``: cambiare la
    password di *un altro* operatore richiede ``EDIT`` sulla sua risorsa
    PERSON, valutato — come ogni decisione ACL — da
    :class:`AuthorizationPolicy` (DESIGN §10; eccezione self-service).
    """
    auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

    # --- Autenticazione locale ---

    @auth_bp.route("/login", methods=["POST"])
    async def local_login():
        body = await parse_json_body()
        username = (body.get("username") or "").strip()
        password = body.get("password", "")
        if not username or not password:
            raise ValidationError("username e password sono obbligatori")
        person, token = await run_blocking(auth_service.login_local, username, password)
        must_change = await run_blocking(
            auth_service.password_change_required, person.id
        )
        return jsonify({
            "token": token,
            "person_id": str(person.id),
            "must_change_password": must_change,
        }), 200

    @auth_bp.route("/logout", methods=["POST"])
    async def local_logout():
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            await run_blocking(auth_service.logout_local, auth_header[7:])
        return jsonify({"ok": True}), 200

    @auth_bp.route("/password", methods=["PUT"])
    async def set_password():
        body = await parse_json_body()
        person_id_raw = body.get("person_id", "")
        password = body.get("password", "")
        if not person_id_raw or not password:
            raise ValidationError("person_id e password sono obbligatori")
        try:
            person_id = UUID(person_id_raw)
        except ValueError:
            raise ValidationError("person_id non valido", field="person_id")

        operator = getattr(g, "operator", None)
        if operator is None:
            raise AuthenticationError("Autenticazione richiesta")
        # Self-service: ognuno può cambiare la propria password. Cambiare quella
        # di un altro operatore richiede EDIT sulla sua risorsa PERSON, deciso
        # dalle AclEntry via AuthorizationPolicy (DESIGN §10) — mai leggendo il
        # profilo direttamente.
        if operator.id != person_id and not await run_blocking(
            auth_policy.is_allowed,
            operator.id,
            Operation.EDIT,
            ResourceRef(ResourceType.PERSON, person_id),
        ):
            raise AuthorizationError(
                "Non autorizzato a modificare la password di un altro operatore"
            )

        # Password impostata da un amministratore per un altro operatore: va
        # cambiata al primo accesso. Il cambio self-service, invece, non forza
        # nulla (l'operatore ha appena scelto la propria password).
        must_change = operator.id != person_id
        await run_blocking(
            auth_service.set_password, person_id, password, must_change
        )
        return jsonify({"ok": True}), 200

    # --- Flusso OIDC (REST / SPA — stateless) ---

    @auth_bp.route("/oidc/url", methods=["GET"])
    async def oidc_auth_url():
        redirect_uri = request.args.get("redirect_uri")
        params = await run_blocking(auth_service.begin_oidc_flow_stateless, redirect_uri)
        return jsonify(params), 200

    @auth_bp.route("/oidc/callback", methods=["POST"])
    async def oidc_callback():
        body = await parse_json_body()
        code = body.get("code", "")
        state = body.get("state", "")
        nonce = body.get("nonce", "")
        code_verifier = body.get("code_verifier", "")
        redirect_uri = body.get("redirect_uri")

        if not code or not state or not nonce or not code_verifier:
            raise ValidationError("code, state, nonce e code_verifier sono obbligatori")

        person, token_set = await run_blocking(
            auth_service.complete_oidc_flow,
            code=code,
            state=state,
            redirect_uri=redirect_uri,
            nonce=nonce,
            code_verifier=code_verifier,
        )
        return jsonify({
            "token": token_set.access_token,
            "person_id": str(person.id),
        }), 200

    return auth_bp
