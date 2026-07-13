# SPDX-License-Identifier: CC-BY-SA-4.0
"""Handler Web App per login/logout locale e callback OIDC.

Route registrate:
  GET  /login          → form locale o redirect OIDC in base ad auth_backend
  POST /login          → verifica credenziali locali, imposta sessione
  GET  /auth/callback  → scambia code OIDC, imposta sessione
  GET  /logout         → cancella sessione locale e, se OIDC, termina la SSO IdP
  POST /logout         → idem (per form submit)
"""
from __future__ import annotations

import html
from typing import Optional
from urllib.parse import urlsplit
from uuid import UUID

from quart import Blueprint, redirect, request, session, url_for, render_template

from ....domain.exceptions import AuthenticationError, AuthorizationError, ValidationError
from ....application.services.auth_service import AuthService
from ....application.services.person_service import PersonService
from ..._http import run_blocking


def _safe_next_url(value: str | None) -> str:
    candidate = (value or "/").strip() or "/"
    if "\\" in candidate or any(ord(char) < 32 or ord(char) == 127 for char in candidate):
        return "/"
    parts = urlsplit(candidate)
    if parts.scheme or parts.netloc:
        return "/"
    if not parts.path.startswith("/"):
        return "/"
    if candidate.startswith("//"):
        return "/"
    return candidate


def register_web_auth_routes(
    bp: Blueprint,
    auth_service: AuthService,
    auth_backend: str,
    oidc_redirect_uri: Optional[str] = None,
    person_svc: Optional[PersonService] = None,
) -> None:
    """Configura il blueprint auth web con il servizio iniettato."""

    SESSION_OIDC_STATE = "oidc_state"
    SESSION_OIDC_NONCE = "oidc_nonce"
    SESSION_OIDC_VERIFIER = "oidc_code_verifier"
    SESSION_OIDC_ID_TOKEN = "oidc_id_token"
    SESSION_NEXT = "oidc_next"
    SESSION_OPERATOR = "operator_id"

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    @bp.route("/login", methods=["GET"])
    async def login_get():
        # Primo avvio locale o person_backend=oidc: se non esiste ancora un
        # amministratore, dirotta sul setup. Con auth OIDC + persone locali,
        # admin_exists è True e il primo login OIDC auto-provisiona l'admin.
        try:
            setup_required = person_svc is not None and not await run_blocking(
                auth_service.admin_exists, person_svc
            )
        except (AuthenticationError, AuthorizationError) as exc:
            return await render_template("error.html", message=exc.message), 503
        if setup_required:
            return redirect(url_for("mission_web.setup_get"))
        if auth_backend == "oidc":
            prompt = "login" if request.args.get("prompt") == "login" else None
            flow = await run_blocking(
                auth_service.begin_oidc_flow, oidc_redirect_uri, prompt
            )
            # Stato del flusso nella sessione Quart firmata: nessuno stato lato
            # server, così il callback funziona con qualsiasi worker (P2).
            session[SESSION_OIDC_STATE] = flow["state"]
            session[SESSION_OIDC_NONCE] = flow["nonce"]
            session[SESSION_OIDC_VERIFIER] = flow["code_verifier"]
            session[SESSION_NEXT] = _safe_next_url(request.args.get("next"))
            return redirect(flow["url"])
        next_url = html.escape(_safe_next_url(request.args.get("next")))
        return await render_template("login.html", next_url=next_url), 200

    @bp.route("/login", methods=["POST"])
    async def login_post():
        form = await request.form
        username = (form.get("username") or "").strip()
        password = form.get("password") or ""
        next_url = _safe_next_url(request.args.get("next") or form.get("next"))
        error_msg: Optional[str] = None
        try:
            person, _token = await run_blocking(
                auth_service.login_local, username, password
            )
            session[SESSION_OPERATOR] = str(person.id)
            # Password impostata da un amministratore: cambio forzato al primo
            # accesso prima di proseguire verso la destinazione richiesta.
            if await run_blocking(
                auth_service.password_change_required, person.id
            ):
                return redirect(
                    url_for("mission_web.change_password_get", next=next_url)
                )
            return redirect(next_url)
        except (AuthenticationError, ValidationError) as exc:
            error_msg = exc.message
        return await render_template("login.html", next_url=next_url, error=error_msg), 401

    # ------------------------------------------------------------------
    # Cambio password (self-service; forzato al primo accesso se richiesto)
    # ------------------------------------------------------------------

    @bp.route("/change-password", methods=["GET"])
    async def change_password_get():
        if not session.get(SESSION_OPERATOR):
            return redirect(url_for("mission_web.login_get"))
        next_url = html.escape(_safe_next_url(request.args.get("next")))
        return await render_template("change_password.html", next_url=next_url), 200

    @bp.route("/change-password", methods=["POST"])
    async def change_password_post():
        operator_id = session.get(SESSION_OPERATOR)
        if not operator_id:
            return redirect(url_for("mission_web.login_get"))

        form = await request.form
        password = form.get("password") or ""
        password2 = form.get("password2") or ""
        next_url = _safe_next_url(request.args.get("next") or form.get("next"))

        error_msg: Optional[str] = None
        if password != password2:
            error_msg = "Le password non coincidono"
        else:
            try:
                # Cambio self-service: azzera il flag must_change_password.
                await run_blocking(
                    auth_service.set_password, UUID(operator_id), password, False
                )
                return redirect(next_url)
            except ValidationError as exc:
                error_msg = exc.message

        return await render_template(
            "change_password.html", next_url=html.escape(next_url), error=error_msg
        ), 400

    # ------------------------------------------------------------------
    # Setup primo avvio (locale o person_backend=oidc, finché manca un admin)
    # ------------------------------------------------------------------
    # Con person_backend=oidc la creazione dell'admin è delegata all'IdP tramite
    # la sua admin API; con persone locali + auth OIDC si passa dal login OIDC.

    @bp.route("/setup", methods=["GET"])
    async def setup_get():
        if person_svc is None:
            return redirect(url_for("mission_web.login_get"))
        try:
            admin_exists = await run_blocking(auth_service.admin_exists, person_svc)
        except (AuthenticationError, AuthorizationError) as exc:
            return await render_template("error.html", message=exc.message), 503
        if admin_exists:
            return redirect(url_for("mission_web.login_get"))
        return await render_template("setup.html"), 200

    @bp.route("/setup", methods=["POST"])
    async def setup_post():
        if person_svc is None:
            return redirect(url_for("mission_web.login_get"))
        try:
            admin_exists = await run_blocking(auth_service.admin_exists, person_svc)
        except (AuthenticationError, AuthorizationError) as exc:
            return await render_template("error.html", message=exc.message), 503
        if admin_exists:
            return redirect(url_for("mission_web.login_get"))

        form = await request.form
        username = (form.get("username") or "").strip()
        password = form.get("password") or ""
        password2 = form.get("password2") or ""

        error_msg: Optional[str] = None
        if not username:
            error_msg = "Il nome utente è obbligatorio"
        elif password != password2:
            error_msg = "Le password non coincidono"
        else:
            try:
                await run_blocking(
                    auth_service.create_initial_admin,
                    person_svc,
                    username,
                    password,
                )
                return redirect(url_for("mission_web.login_get"))
            except (ValidationError, AuthenticationError) as exc:
                error_msg = exc.message

        return await render_template("setup.html", error=error_msg, username=username), 400

    # ------------------------------------------------------------------
    # OIDC callback
    # ------------------------------------------------------------------

    @bp.route("/auth/callback", methods=["GET"])
    async def oidc_callback():
        code = request.args.get("code", "")
        state = request.args.get("state", "")
        error = request.args.get("error")
        if error:
            return await render_template("error.html", message=f"OIDC error: {html.escape(error)}"), 401

        expected_state = session.pop(SESSION_OIDC_STATE, None)
        nonce = session.pop(SESSION_OIDC_NONCE, None)
        code_verifier = session.pop(SESSION_OIDC_VERIFIER, None)
        if not code or not state or state != expected_state or not nonce or not code_verifier:
            return await render_template("error.html", message="Callback OIDC non valido (state mismatch)"), 400

        next_url = _safe_next_url(session.pop(SESSION_NEXT, "/"))
        try:
            person, token_set = await run_blocking(
                auth_service.complete_oidc_flow,
                code,
                state,
                nonce,
                code_verifier,
            )
            session[SESSION_OPERATOR] = str(person.id)
            session[SESSION_OIDC_ID_TOKEN] = getattr(token_set, "id_token", "")
            return redirect(next_url)
        except AuthenticationError as exc:
            return await render_template("error.html", message=f"Autenticazione OIDC fallita: {html.escape(exc.message)}"), 401

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    @bp.route("/logout", methods=["GET", "POST"])
    async def logout():
        id_token_hint = session.get(SESSION_OIDC_ID_TOKEN) if auth_backend == "oidc" else None
        session.clear()
        if auth_backend == "oidc":
            post_logout_redirect = url_for("mission_web.login_get", _external=True)
            try:
                logout_url = await run_blocking(
                    auth_service.build_oidc_logout_url,
                    post_logout_redirect,
                    id_token_hint,
                )
            except AuthenticationError:
                logout_url = None
            if logout_url:
                return redirect(logout_url)
            return redirect(url_for("mission_web.login_get", prompt="login"))
        return redirect("/login")

    return None
