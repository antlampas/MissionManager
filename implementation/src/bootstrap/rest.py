# SPDX-License-Identifier: CC-BY-SA-4.0
"""Bootstrap REST API frontend."""
from __future__ import annotations

import os
from typing import Optional

from ..infrastructure.auth.local import LocalAuthAdapter
from ..infrastructure.identity.rest import RestOperatorIdentityAdapter
from ..config import SecurityConfig, SecurityConfigLoader
from ..frontend.api.app import RestApp
from .common import build_system


def _validate_rest_oidc_config(cfg: SecurityConfig) -> None:
    """Valida i parametri OIDC indispensabili alla validazione dei Bearer token REST.

    Senza ``jwks_url`` l'adapter non può verificare la firma → 401 su tutto;
    senza ``audience`` PyJWT rifiuta i token che contengono il claim ``aud`` →
    di nuovo 401 generalizzato. Si fallisce qui con un messaggio chiaro invece
    di lasciare un 401 opaco a runtime (P3).
    """
    if cfg.auth_backend != "oidc":
        return
    missing = [
        name
        for name, value in (
            ("oidc_jwks_url (MISSIONMANAGER_OIDC_JWKS_URL)", cfg.oidc_jwks_url),
            ("oidc_audience (MISSIONMANAGER_OIDC_AUDIENCE)", cfg.oidc_audience),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "REST API con auth_backend=oidc richiede: " + ", ".join(missing)
        )


def create_rest_app(config_file: Optional[str] = None):
    """Returns a ready-to-serve ASGI callable for the REST API.

    ``config_file`` è il path del file di configurazione; se ``None`` viene letto
    da ``MISSIONMANAGER_CONFIG_FILE``. Serve with Hypercorn (or any ASGI server)
    — do not call app.run().
    """
    resolved_config = config_file or os.environ.get("MISSIONMANAGER_CONFIG_FILE")
    security_config = SecurityConfigLoader.load(resolved_config)
    _validate_rest_oidc_config(security_config)
    svcs = build_system(resolved_config)

    local_auth: Optional[LocalAuthAdapter] = None
    if security_config.auth_backend == "local":
        local_auth = svcs.auth_service._local_auth

    identity_provider = RestOperatorIdentityAdapter(
        person_repo=svcs.person_repo,
        local_auth=local_auth,
        jwks_url=security_config.oidc_jwks_url,
        audience=security_config.oidc_audience,
        issuer=security_config.oidc_issuer,
        dev_mode=security_config.rest_dev_mode,
        uow=svcs.uow,
    )

    app = RestApp(
        mission_svc=svcs.mission,
        assignment_svc=svcs.assignment,
        activity_svc=svcs.activity,
        badge_svc=svcs.badge,
        person_svc=svcs.person,
        acl_svc=svcs.acl,
        extension_registry=svcs.extension_registry,
        auth_policy=svcs.auth_policy,
        identity_provider=identity_provider,
        auth_service=svcs.auth_service,
        secret_key=security_config.secret_key,
        rate_limit_policy=svcs.rate_limit_policy,
        event_publisher=svcs.event_publisher,
    )
    return app.app, svcs
