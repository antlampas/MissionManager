# SPDX-License-Identifier: CC-BY-SA-4.0
import asyncio
from typing import Optional

from quart import Quart, g, jsonify, request

from ...domain.acl import Operation, ResourceRef, SYSTEM_RESOURCE
from ...domain.enums import ResourceType
from ...domain.exceptions import ACLError, AuthenticationError, RateLimitExceededError
from ...domain.identity import OperatorIdentityProvider
from ...application.authorization import AuthorizationPolicy
from ...application.services._shared import reset_current_operator_id, set_current_operator_id
from ...infrastructure.security.rate_limit import (
    InMemoryRateLimitPolicy,
    NoOpRateLimitPolicy,
    RateLimitedOperation,
)

_READONLY_METHODS = frozenset(("GET", "HEAD", "OPTIONS"))

# Prefissi esclusi dall'autenticazione (endpoint pubblici).
# /api/auth/password NON è incluso: richiede un Bearer token valido.
_PUBLIC_PREFIXES = (
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/oidc/",
)

# Route la cui autorizzazione è applicata dal service (autoprotezione di
# AclService via MANAGE_ACL, self-service del cambio password nel router
# auth): il middleware richiede la sola autenticazione.
_SERVICE_ENFORCED_PREFIXES = (
    "/api/acl/",
    "/api/auth/password",
)

_WWW_AUTH = 'Bearer realm="missionmanager"'


def _rate_limited_operation(path: str, method: str):
    if method == "POST" and path == "/api/missions":
        return RateLimitedOperation.CREATE_MISSION
    if method == "DELETE" and path.startswith("/api/missions/"):
        return RateLimitedOperation.DELETE_MISSION
    if method == "POST" and path.endswith("/assignments"):
        return RateLimitedOperation.CREATE_ASSIGNMENT
    if method == "POST" and path.endswith("/assign") and "/assignments/" in path:
        return RateLimitedOperation.ASSIGN_ASSIGNMENT
    if method == "PUT" and path.endswith("/status") and "/assignments/" in path:
        return RateLimitedOperation.UPDATE_ASSIGNMENT_STATUS
    if method == "PUT" and path.endswith("/status") and "/activities/" in path:
        return RateLimitedOperation.UPDATE_ACTIVITY_STATUS
    if method == "POST" and path.endswith("/assign") and "/activities/" in path:
        return RateLimitedOperation.ASSIGN_ACTIVITY
    if method == "DELETE" and path.endswith("/assign") and "/activities/" in path:
        return RateLimitedOperation.UNASSIGN_ACTIVITY
    if method == "POST" and path == "/api/badges":
        return RateLimitedOperation.CREATE_BADGE
    if method == "POST" and path.endswith("/badge"):
        return RateLimitedOperation.AWARD_BADGE
    if method == "POST" and path == "/api/persons":
        return RateLimitedOperation.ADD_PERSON
    if method == "PUT" and path.startswith("/api/persons/"):
        return RateLimitedOperation.UPDATE_PERSON
    if method == "DELETE" and path.startswith("/api/persons/"):
        return RateLimitedOperation.REMOVE_PERSON
    if method == "POST" and path == "/api/groups":
        return RateLimitedOperation.CREATE_GROUP
    if method == "PUT" and path.startswith("/api/groups/"):
        return RateLimitedOperation.UPDATE_GROUP
    if method == "POST" and path.endswith("/members") and "/groups/" in path:
        return RateLimitedOperation.ADD_GROUP_MEMBER
    if method == "DELETE" and path.endswith("/members") and "/groups/" in path:
        return RateLimitedOperation.REMOVE_GROUP_MEMBER
    if method == "DELETE" and path.startswith("/api/groups/"):
        return RateLimitedOperation.REMOVE_GROUP
    if method == "PUT" and path == "/api/auth/password":
        return RateLimitedOperation.CHANGE_PASSWORD
    if method not in _READONLY_METHODS:
        # Mantiene protette anche route d'estensione mutanti, per le quali il
        # middleware non conosce in anticipo il verbo di dominio.
        return RateLimitedOperation.OTHER_MUTATION
    return None


# Mappa (rule Quart, metodo) → (Operation, tipo risorsa, nome del view-arg con
# l'id — None per la radice di tipo o SYSTEM). L'enforcement primario avviene
# qui, al confine; i service ricontrollano come difesa in profondità quando
# ricevono un operatore o un contesto frontend/CLI.
_SYSTEM = ("SYSTEM", None)
_ROUTE_OPERATIONS: dict[tuple[str, str], tuple[Operation, str, Optional[str]]] = {
    # --- Missioni ---
    ("/api/missions", "GET"): (Operation.LIST, "MISSION", None),
    ("/api/missions", "POST"): (Operation.CREATE_MISSION, *_SYSTEM),
    ("/api/missions/<uuid:id>", "GET"): (Operation.VIEW, "MISSION", "id"),
    ("/api/missions/<uuid:id>", "DELETE"): (Operation.DELETE, "MISSION", "id"),
    ("/api/missions/<uuid:id>/objectives", "GET"): (Operation.VIEW, "MISSION", "id"),
    # --- Assegnazioni ---
    ("/api/missions/<uuid:mission_id>/assignments", "GET"): (
        Operation.LIST, "MISSION", "mission_id"),
    ("/api/missions/<uuid:mission_id>/assignments", "POST"): (
        Operation.CREATE_ASSIGNMENT, "MISSION", "mission_id"),
    ("/api/assignments/<uuid:id>", "GET"): (Operation.VIEW, "ASSIGNMENT", "id"),
    ("/api/assignments/<uuid:id>/assign", "POST"): (Operation.ASSIGN, "ASSIGNMENT", "id"),
    ("/api/assignments/<uuid:id>/status", "PUT"): (
        Operation.UPDATE_STATUS, "ASSIGNMENT", "id"),
    ("/api/assignments/<uuid:id>/badge", "POST"): (
        Operation.AWARD_BADGE, "ASSIGNMENT", "id"),
    ("/api/assignments/<uuid:id>/objectives", "GET"): (Operation.VIEW, "ASSIGNMENT", "id"),
    # --- Attività ---
    ("/api/activities/<uuid:id>", "GET"): (Operation.VIEW, "ACTIVITY", "id"),
    ("/api/activities/<uuid:id>/status", "PUT"): (
        Operation.UPDATE_STATUS, "ACTIVITY", "id"),
    ("/api/activities/<uuid:id>/assign", "POST"): (Operation.ASSIGN, "ACTIVITY", "id"),
    ("/api/activities/<uuid:id>/assign", "DELETE"): (Operation.ASSIGN, "ACTIVITY", "id"),
    ("/api/activities/<uuid:id>/badge", "POST"): (
        Operation.AWARD_BADGE, "ACTIVITY", "id"),
    ("/api/objectives/<uuid:id>/activities", "GET"): (Operation.LIST, "OBJECTIVE", "id"),
    # --- Badge ---
    ("/api/badges", "GET"): (Operation.LIST, "BADGE", None),
    ("/api/badges", "POST"): (Operation.CREATE_BADGE, *_SYSTEM),
    ("/api/badges/<uuid:id>", "GET"): (Operation.VIEW, "BADGE", "id"),
    ("/api/persons/<uuid:id>/badges", "GET"): (Operation.VIEW, "PERSON", "id"),
    # --- Persone ---
    ("/api/persons", "GET"): (Operation.LIST, "PERSON", None),
    ("/api/persons", "POST"): (Operation.CREATE_PERSON, *_SYSTEM),
    ("/api/persons/<uuid:id>", "GET"): (Operation.VIEW, "PERSON", "id"),
    ("/api/persons/<uuid:id>", "PUT"): (Operation.EDIT, "PERSON", "id"),
    ("/api/persons/<uuid:id>", "DELETE"): (Operation.DELETE, "PERSON", "id"),
    # Assegnazione del profilo ACL: fuori dal catalogo delegabile (DESIGN §10).
    ("/api/persons/<uuid:id>/acl", "PUT"): (Operation.MANAGE_PROFILES, *_SYSTEM),
    # --- Gruppi ---
    ("/api/groups", "GET"): (Operation.LIST, "GROUP", None),
    ("/api/groups", "POST"): (Operation.CREATE_GROUP, *_SYSTEM),
    ("/api/groups/<uuid:id>", "GET"): (Operation.VIEW, "GROUP", "id"),
    ("/api/groups/<uuid:id>", "PUT"): (Operation.EDIT, "GROUP", "id"),
    ("/api/groups/<uuid:id>", "DELETE"): (Operation.DELETE, "GROUP", "id"),
    ("/api/groups/<uuid:id>/members", "GET"): (Operation.VIEW, "GROUP", "id"),
    ("/api/groups/<uuid:id>/members", "POST"): (Operation.MANAGE_MEMBERS, "GROUP", "id"),
    ("/api/groups/<uuid:id>/members", "DELETE"): (Operation.MANAGE_MEMBERS, "GROUP", "id"),
}


def _resolve_check(rule: Optional[str], method: str, view_args: dict):
    """Risolve (Operation, ResourceRef) per la richiesta corrente.

    Route non mappate (estensioni): VIEW su SYSTEM per le letture, EXECUTE su
    SYSTEM per le mutazioni — governate dalle entry di ambito sistema.
    """
    mapped = _ROUTE_OPERATIONS.get((rule or "", method))
    if mapped is None:
        if method in _READONLY_METHODS:
            return Operation.VIEW, SYSTEM_RESOURCE
        return Operation.EXECUTE, SYSTEM_RESOURCE
    operation, type_name, arg_name = mapped
    resource_type = ResourceType(type_name)
    if resource_type == ResourceType.SYSTEM:
        return operation, SYSTEM_RESOURCE
    if arg_name is None:
        return operation, ResourceRef.type_root(resource_type)
    return operation, ResourceRef(resource_type, view_args.get(arg_name))


class AuthMiddleware:
    """Enforcement ACL al confine REST (DESIGN §10).

    Risolve l'identità dell'operatore (assente → profilo anonimo implicito),
    mappa la richiesta su ``(Operation, ResourceRef)`` e interroga
    ``AuthorizationPolicy.is_allowed``:

    - DENIED e richiedente anonimo → 401 + WWW-Authenticate
    - DENIED e richiedente autenticato → 403
    - Percorsi pubblici (login/logout/OIDC) saltano la verifica; le route ACL
      e il cambio password sono autorizzate dal service/router (il middleware
      richiede solo l'autenticazione).
    """

    def __init__(
        self,
        app: Quart,
        identity_provider: OperatorIdentityProvider,
        auth_policy: AuthorizationPolicy,
        rate_limit_policy: InMemoryRateLimitPolicy | NoOpRateLimitPolicy | None = None,
    ) -> None:
        @app.before_request
        async def check_acl():
            path = request.path or ""

            # Percorsi pubblici — skip autenticazione
            if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
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

            if any(path.startswith(p) for p in _SERVICE_ENFORCED_PREFIXES):
                if operator is None:
                    return (
                        jsonify({"error": "Autenticazione richiesta"}),
                        401,
                        {"WWW-Authenticate": _WWW_AUTH},
                    )
            else:
                rule = request.url_rule.rule if request.url_rule is not None else None
                operation, resource = _resolve_check(
                    rule, request.method, request.view_args or {}
                )
                allowed = await asyncio.to_thread(
                    auth_policy.is_allowed,
                    operator.id if operator is not None else None,
                    operation,
                    resource,
                )
                if not allowed:
                    if operator is None:
                        return (
                            jsonify({"error": "Autenticazione richiesta"}),
                            401,
                            {"WWW-Authenticate": _WWW_AUTH},
                        )
                    return jsonify({"error": "Accesso negato dalle ACL"}), 403

            if operator is not None:
                rate_op = _rate_limited_operation(path, request.method)
                if rate_op is not None and rate_limit_policy is not None:
                    try:
                        rate_limit_policy.check(operator.id, rate_op)
                    except RateLimitExceededError as exc:
                        return (
                            jsonify(
                                {"error": exc.message, "limit": exc.limit, "window": exc.window}
                            ),
                            429,
                        )

            return None

        @app.after_request
        async def reset_operator_context(response):
            token = getattr(g, "_operator_context_token", None)
            if token is not None:
                reset_current_operator_id(token)
            return response
