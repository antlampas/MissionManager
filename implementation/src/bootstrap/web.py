# SPDX-License-Identifier: CC-BY-SA-4.0
"""Bootstrap Web App (async) frontend."""
from __future__ import annotations

import os
from typing import Optional
from quart import Quart

from ..infrastructure.identity.web import WebOperatorIdentityAdapter
from ..config import RealtimeConfigLoader, SecurityConfigLoader, WebConfigLoader
from ..frontend.web.app import create_web_blueprint
from .common import build_system


def create_web_app(config_file: Optional[str] = None):
    """Restituisce una coppia ``(app, system)`` pronta per Hypercorn/Uvicorn.

    ``config_file`` è il path del file di configurazione; se ``None`` viene letto
    da ``MISSIONMANAGER_CONFIG_FILE``. Non chiamare ``app.run()`` direttamente —
    usare un ASGI server.
    """
    resolved_config = config_file or os.environ.get("MISSIONMANAGER_CONFIG_FILE")
    security_config = SecurityConfigLoader.load(resolved_config)
    web_config = WebConfigLoader.load(resolved_config)
    realtime_config = RealtimeConfigLoader.load(resolved_config)
    svcs = build_system(resolved_config)

    # static_folder=None disabilita la route static di default dell'app (che
    # punterebbe a src/bootstrap/static, inesistente). Senza questo, la sua
    # regola /static/<filename> verrebbe registrata per prima e oscurerebbe
    # quella del blueprint (mission_web.static), facendo restituire 404 a
    # /static/app.js e /static/style.css.
    app = Quart(__name__, static_folder=None)

    if not security_config.secret_key:
        raise RuntimeError(
            "secret_key è obbligatoria per la Web App. "
            "Imposta MISSIONMANAGER_SECRET_KEY."
        )
    app.secret_key = security_config.secret_key

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Secure (HTTPS-only) per default; in dev locale su HTTP va messo a False
    # (MISSIONMANAGER_WEB_SECURE_COOKIES=false), altrimenti il browser scarta
    # il cookie di sessione e login/setup falliscono per CSRF.
    app.config["SESSION_COOKIE_SECURE"] = web_config.secure_cookies

    identity_provider = WebOperatorIdentityAdapter(
        person_repo=svcs.person_repo,
        uow=svcs.uow,
    )

    bp = create_web_blueprint(
        mission_svc=svcs.mission,
        assignment_svc=svcs.assignment,
        activity_svc=svcs.activity,
        person_svc=svcs.person,
        badge_svc=svcs.badge,
        acl_svc=svcs.acl,
        auth_policy=svcs.auth_policy,
        identity_provider=identity_provider,
        auth_service=svcs.auth_service,
        auth_backend=security_config.auth_backend,
        oidc_redirect_uri=security_config.oidc_redirect_uri,
        theme=web_config.theme,
        event_publisher=svcs.event_publisher,
        redis_url=realtime_config.redis_url,
        redis_prefix=realtime_config.redis_prefix,
        extension_registry=svcs.extension_registry,
    )

    app.register_blueprint(bp)

    return app, svcs
