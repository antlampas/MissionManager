# SPDX-License-Identifier: CC-BY-SA-4.0
"""Enforcement ACL al confine della Web App (DESIGN §10).

Il middleware risolve l'identità dell'operatore (assente → profilo anonimo
implicito), mappa l'endpoint Quart della richiesta su ``(Operation,
ResourceRef)`` e interroga ``AuthorizationPolicy.is_allowed``:

- DENIED e richiedente anonimo → redirect al login (mutazioni: 401 JSON)
- DENIED e richiedente autenticato → 403 JSON
- Percorsi in ``public_prefixes`` sono esclusi dal controllo.

Le route che gestiscono le AclEntry sono autorizzate dal service stesso
(autoprotezione MANAGE_ACL di AclService); qui è richiesta la sola
autenticazione.
"""
from typing import Optional
from urllib.parse import quote
import asyncio

from quart import g, jsonify, redirect, request, url_for

from ...domain.acl import Operation, ResourceRef, SYSTEM_RESOURCE
from ...domain.enums import ResourceType
from ...domain.exceptions import ACLError, AuthenticationError
from ...domain.identity import OperatorIdentityProvider
from ...application.authorization import AuthorizationPolicy
from ...application.services._shared import reset_current_operator_id, set_current_operator_id

_READONLY_METHODS = frozenset(("GET", "HEAD", "OPTIONS"))

# Percorsi pubblici — skip autenticazione.
# "/ws" è gestito dall'handler WebSocket stesso (chiude con 1008).
# "/change-password" è self-service: l'autenticazione è verificata dall'handler
# stesso (sessione operatore), non dal middleware ACL.
_DEFAULT_PUBLIC_PREFIXES = (
    "/login", "/auth/", "/logout", "/static/", "/ws", "/setup", "/change-password",
)

# Sentinella per gli endpoint autorizzati dal service (gestione AclEntry):
# il middleware richiede solo l'autenticazione.
SERVICE_ENFORCED = object()

# Mappa endpoint Quart → (Operation, tipo risorsa, nome del view-arg con l'id;
# None = radice di tipo o SYSTEM). I form di creazione sono mappati
# sull'operazione a cui conducono, così chi non può creare non vede il form.
EndpointACL = dict[str, object]


class ACLMiddleware:
    def __init__(
        self,
        app,
        identity_provider: OperatorIdentityProvider,
        auth_policy: AuthorizationPolicy,
        endpoint_acl: Optional[EndpointACL] = None,
        login_endpoint: str = "mission_web.login_get",
        public_prefixes: tuple[str, ...] = _DEFAULT_PUBLIC_PREFIXES,
    ) -> None:
        endpoint_acl = endpoint_acl or {}

        def _resolve_check(endpoint: str, view_args: dict):
            mapped = endpoint_acl.get(endpoint)
            if mapped is SERVICE_ENFORCED:
                return SERVICE_ENFORCED
            if mapped is None:
                # Endpoint non mappati (estensioni): entry di ambito sistema.
                if request.method in _READONLY_METHODS:
                    return Operation.VIEW, SYSTEM_RESOURCE
                return Operation.EXECUTE, SYSTEM_RESOURCE
            operation, type_name, arg_name = mapped
            resource_type = ResourceType(type_name)
            if resource_type == ResourceType.SYSTEM:
                return operation, SYSTEM_RESOURCE
            if arg_name is None:
                return operation, ResourceRef.type_root(resource_type)
            return operation, ResourceRef(resource_type, view_args.get(arg_name))

        def _deny(operator):
            if operator is None:
                if request.method in _READONLY_METHODS:
                    next_url = quote(str(request.url), safe="")
                    try:
                        login_url = url_for(login_endpoint, next=next_url)
                    except Exception:
                        login_url = f"/login?next={next_url}"
                    return redirect(login_url)
                return jsonify({"error": "Autenticazione richiesta"}), 401
            return jsonify({"error": "Accesso negato dalle ACL"}), 403

        @app.before_request
        async def check_acl():
            path = request.path or ""

            if any(path.startswith(p) for p in public_prefixes):
                return None

            try:
                operator = await asyncio.to_thread(identity_provider.get_current_operator)
            except AuthenticationError:
                operator = None  # profilo anonimo implicito (DESIGN §10)
            except ACLError as exc:
                return jsonify({"error": exc.message}), 403

            g.operator = operator
            g._operator_context_token = set_current_operator_id(
                operator.id if operator is not None else None
            )

            check = _resolve_check(request.endpoint or "", request.view_args or {})
            if check is SERVICE_ENFORCED:
                if operator is None:
                    return _deny(None)
                return None

            operation, resource = check
            allowed = await asyncio.to_thread(
                auth_policy.is_allowed,
                operator.id if operator is not None else None,
                operation,
                resource,
            )
            if not allowed:
                return _deny(operator)
            return None

        @app.after_request
        async def reset_operator_context(response):
            token = getattr(g, "_operator_context_token", None)
            if token is not None:
                reset_current_operator_id(token)
            return response
