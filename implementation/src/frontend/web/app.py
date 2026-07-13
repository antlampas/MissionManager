# SPDX-License-Identifier: CC-BY-SA-4.0
"""Quart Blueprint factory per la Web App Mission Manager.

Può essere registrata su qualsiasi applicazione Quart::

    from src.frontend.web.app import create_web_blueprint

    bp = create_web_blueprint(
        mission_svc=...,
        assignment_svc=...,
        activity_svc=...,
        ...
    )
    app.register_blueprint(bp)                    # radice; url_prefix non supportato

Attributi pubblici esposti sul Blueprint restituito:
    bp.notifier  (RealtimeNotifier) — accesso esterno al bus WebSocket

Sistema di temi
---------------
I temi risiedono in due directory parallele::

    frontend/web/
        static/<theme>/style.css   (obbligatorio)
        static/<theme>/app.js      (opzionale)
        templates/<theme>/         (opzionale — sovrascrive solo i template necessari)
        templates/default/         (fallback per ogni template non presente nel tema)

Selezionare il tema via ``WebConfig.theme`` (default: ``"default"``).
"""
from __future__ import annotations

import logging
import asyncio
from pathlib import Path
from typing import Optional

from jinja2 import ChoiceLoader, FileSystemLoader
from quart import Blueprint, g, jsonify, request, send_from_directory

from ...application.authorization import AuthorizationPolicy
from ...application.services.acl_service import AclService
from ...application.services.activity_service import ActivityService
from ...application.services.assignment_service import AssignmentService
from ...application.services.auth_service import AuthService
from ...application.services.badge_service import BadgeService
from ...application.services.mission_service import MissionService
from ...application.services.person_service import PersonService
from ...domain.acl import Operation, SYSTEM_RESOURCE
from ...domain.exceptions import (
    ACLError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    OperationAbortedError,
    StatusTransitionError,
    ValidationError,
)
from ...domain.identity import OperatorIdentityProvider
from ...domain.extensions import ExtensionRequest
from ...infrastructure.identity.web import WebOperatorIdentityAdapter
from .handlers.acl import AclRouteHandler
from .handlers.activities import ActivityRouteHandler
from .handlers.assignments import AssignmentRouteHandler
from .handlers.auth import register_web_auth_routes
from .handlers.badges import BadgeRouteHandler
from .handlers.groups import GroupRouteHandler
from .handlers.missions import MissionRouteHandler
from .handlers.objectives import ObjectiveRouteHandler
from .handlers.persons import PersonRouteHandler
from .middleware import ACLMiddleware, SERVICE_ENFORCED
from .notifier import RealtimeNotifier
from .csrf import get_csrf_token, validate_csrf_request

_log = logging.getLogger(__name__)

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # connect-src include ws:/wss: per il WebSocket real-time;
    # img-src consente le immagini dei badge ospitate su URL https esterni.
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
        "form-action 'self'; object-src 'none'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' https: data:; connect-src 'self' ws: wss:"
    ),
}


# Mappa endpoint Quart → (Operation, tipo risorsa, view-arg con l'id; None =
# radice di tipo o SYSTEM). È la tabella di enforcement del confine Web
# (DESIGN §10): il middleware la interroga a ogni richiesta. I form di
# creazione sono mappati sull'operazione a cui conducono. Le route di gestione
# delle AclEntry sono SERVICE_ENFORCED: autorizzate da AclService (MANAGE_ACL).
_SYSTEM = ("SYSTEM", None)
_WEB_ENDPOINT_ACL: dict[str, object] = {
    # --- Missioni ---
    "mission_web.list_missions": (Operation.LIST, "MISSION", None),
    "mission_web.new_mission_form": (Operation.CREATE_MISSION, *_SYSTEM),
    "mission_web.create_mission": (Operation.CREATE_MISSION, *_SYSTEM),
    "mission_web.get_mission": (Operation.VIEW, "MISSION", "id"),
    "mission_web.delete_mission": (Operation.DELETE, "MISSION", "id"),
    # --- Assegnazioni ---
    "mission_web.list_assignments": (Operation.LIST, "ASSIGNMENT", None),
    # Il form globale non riferisce una missione specifica: si valuta sulla
    # radice di tipo (la delega per-missione resta disponibile via REST).
    "mission_web.new_assignment_form": (Operation.CREATE_ASSIGNMENT, "MISSION", None),
    "mission_web.create_assignment": (Operation.CREATE_ASSIGNMENT, "MISSION", None),
    "mission_web.get_assignment": (Operation.VIEW, "ASSIGNMENT", "id"),
    "mission_web.assign_assignment": (Operation.ASSIGN, "ASSIGNMENT", "id"),
    "mission_web.update_assignment_status": (Operation.UPDATE_STATUS, "ASSIGNMENT", "id"),
    "mission_web.award_assignment_badge": (Operation.AWARD_BADGE, "ASSIGNMENT", "id"),
    "mission_web.list_objectives": (Operation.VIEW, "ASSIGNMENT", "id"),
    # --- Attività ---
    "mission_web.get_activity": (Operation.VIEW, "ACTIVITY", "id"),
    "mission_web.update_activity_status": (Operation.UPDATE_STATUS, "ACTIVITY", "id"),
    "mission_web.assign_to_activity": (Operation.ASSIGN, "ACTIVITY", "id"),
    "mission_web.unassign_from_activity": (Operation.ASSIGN, "ACTIVITY", "id"),
    "mission_web.award_activity_badge": (Operation.AWARD_BADGE, "ACTIVITY", "id"),
    # --- Persone ---
    "mission_web.list_persons": (Operation.LIST, "PERSON", None),
    "mission_web.new_person_form": (Operation.CREATE_PERSON, *_SYSTEM),
    "mission_web.create_person": (Operation.CREATE_PERSON, *_SYSTEM),
    "mission_web.get_person": (Operation.VIEW, "PERSON", "id"),
    "mission_web.update_person": (Operation.EDIT, "PERSON", "id"),
    "mission_web.delete_person": (Operation.DELETE, "PERSON", "id"),
    # --- Gruppi ---
    "mission_web.list_groups": (Operation.LIST, "GROUP", None),
    "mission_web.new_group_form": (Operation.CREATE_GROUP, *_SYSTEM),
    "mission_web.create_group": (Operation.CREATE_GROUP, *_SYSTEM),
    "mission_web.get_group": (Operation.VIEW, "GROUP", "id"),
    "mission_web.update_group": (Operation.EDIT, "GROUP", "id"),
    "mission_web.delete_group": (Operation.DELETE, "GROUP", "id"),
    "mission_web.add_group_member": (Operation.MANAGE_MEMBERS, "GROUP", "id"),
    "mission_web.remove_group_member": (Operation.MANAGE_MEMBERS, "GROUP", "id"),
    # --- Badge ---
    "mission_web.list_badges": (Operation.LIST, "BADGE", None),
    "mission_web.new_badge_form": (Operation.CREATE_BADGE, *_SYSTEM),
    "mission_web.create_badge": (Operation.CREATE_BADGE, *_SYSTEM),
    "mission_web.get_badge": (Operation.VIEW, "BADGE", "id"),
    # --- ACL: pagina di amministrazione e profili ---
    "mission_web.acl_management": (Operation.MANAGE_ACL, *_SYSTEM),
    "mission_web.set_acl_profile": (Operation.MANAGE_PROFILES, *_SYSTEM),
    "mission_web.remove_acl_profile_group": (Operation.MANAGE_PROFILES, *_SYSTEM),
    # --- ACL: entry (autoprotette da MANAGE_ACL in AclService) ---
    "mission_web.create_acl_entry": SERVICE_ENFORCED,
    "mission_web.delete_acl_entry": SERVICE_ENFORCED,
}


def _resolve_theme(theme: str) -> str:
    """Valida il tema; torna a 'default' se la sua directory static non esiste."""
    if theme != "default" and not (_STATIC_DIR / theme).is_dir():
        _log.warning(
            "Web theme '%s' non trovato in static/; fallback a 'default'", theme
        )
        return "default"
    return theme


def _asset_version(theme: str) -> str:
    """Versione cache-busting per gli asset statici (mtime più recente).

    Gli asset sono serviti con ``Cache-Control: max-age`` lungo; senza un token
    di versione nell'URL il browser continuerebbe a usare la copia in cache anche
    dopo una modifica a ``app.js`` o al CSS del tema. Appendendo ``?v=<mtime>``
    agli URL, una moditica a uno di questi file ne cambia l'URL e forza il
    re-fetch, mentre i file invariati restano in cache.
    """
    # app.js vive sempre nel tema default; il CSS dipende dal tema risolto.
    candidates = [_STATIC_DIR / "default" / "app.js", _STATIC_DIR / theme / "style.css"]
    latest = 0.0
    for path in candidates:
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return str(int(latest))


def _build_extension_view(ext_id: str, extension_registry):
    async def extension_view(**kwargs):
        operator = getattr(g, "operator", None)
        params = dict(request.args)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            body = await request.get_json(silent=True)
            if body is not None:
                if not isinstance(body, dict):
                    raise ValidationError("Il body JSON deve essere un oggetto", field="body")
                params.update(body)
        params.update(kwargs)
        result = extension_registry.execute(
            ext_id,
            ExtensionRequest(
                operator_id=operator.id if operator else None,
                params=params,
                body=params,
            ),
        )
        return jsonify({"data": result.data, "message": result.message}), result.status_code

    extension_view.__name__ = f"web_ext_{ext_id}"
    return extension_view


def create_web_blueprint(
    mission_svc: MissionService,
    assignment_svc: AssignmentService,
    activity_svc: ActivityService,
    person_svc: PersonService,
    identity_provider: OperatorIdentityProvider,
    auth_policy: AuthorizationPolicy,
    badge_svc: Optional[BadgeService] = None,
    acl_svc: Optional[AclService] = None,
    auth_service: Optional[AuthService] = None,
    auth_backend: str = "local",
    oidc_redirect_uri: Optional[str] = None,
    theme: str = "default",
    event_publisher=None,
    redis_url: Optional[str] = None,
    redis_prefix: str = "missionmanager",
    extension_registry=None,
) -> Blueprint:
    """Crea il Blueprint Quart per la Web App.

    Parameters
    ----------
    mission_svc:        servizio delle missioni
    assignment_svc:     servizio degli assignment
    activity_svc:       servizio delle attività
    person_svc:         servizio delle persone
    identity_provider:  estrattore dell'operatore corrente dalla sessione
    auth_policy:        la decisione ACL pura (``is_allowed``), interrogata dal
        middleware per ogni endpoint secondo ``_WEB_ENDPOINT_ACL`` (DESIGN §10)
    acl_svc:            servizio di gestione delle AclEntry; abilita la pagina
        di amministrazione ``/acl`` (profili + entry)
    auth_service:       se fornito, registra le route /login /logout /auth/callback
    auth_backend:       "local" | "oidc"
    oidc_redirect_uri:  URI di callback OIDC (solo se auth_backend="oidc")
    theme:              nome del tema (directory sotto static/ e templates/)
    """
    resolved_theme = _resolve_theme(theme)

    bp = Blueprint(
        "mission_web",
        __name__,
        # template_folder NON impostato: gestito dal ChoiceLoader in record_once
        # Il JavaScript comune vive sempre nel tema default.  Il CSS del tema
        # viene invece esposto dalla route dedicata qui sotto.
        static_folder="static/default",
        static_url_path="/static",
    )

    # ------------------------------------------------------------------
    # Fallback template loader: tema → default
    # Temi CSS-only non richiedono alcuna directory templates/<theme>/;
    # temi HTML parziali sovrascrivono solo i file che contengono.
    # ------------------------------------------------------------------
    @bp.record_once
    def _setup_template_loader(state) -> None:
        from jinja2 import ChoiceLoader, FileSystemLoader

        loaders: list = []
        if resolved_theme != "default":
            td = _TEMPLATES_DIR / resolved_theme
            if td.is_dir():
                loaders.append(FileSystemLoader(str(td)))
        loaders.append(FileSystemLoader(str(_TEMPLATES_DIR / "default")))

        bp_loader = ChoiceLoader(loaders)
        env = state.app.jinja_env          # inizializza l'env se non esiste
        env.loader = ChoiceLoader([env.loader, bp_loader]) if env.loader else bp_loader

    # ------------------------------------------------------------------
    # Contesto globale per tutti i template
    # ------------------------------------------------------------------
    @bp.context_processor
    async def _inject_ctx() -> dict:
        return {
            "current_operator": getattr(g, "operator", None),
            "web_theme": resolved_theme,
            "csrf_token": get_csrf_token(),
            "badges_enabled": badge_svc is not None,
            "asset_version": _asset_version(resolved_theme),
        }

    @bp.before_request
    async def _check_csrf():
        await validate_csrf_request()

    @bp.route("/static/theme.css", endpoint="theme_style", methods=["GET"])
    async def theme_style():
        return await send_from_directory(_STATIC_DIR / resolved_theme, "style.css")

    # ------------------------------------------------------------------
    # Handler e notifier
    # ------------------------------------------------------------------
    notifier = RealtimeNotifier()
    bp.notifier = notifier  # attributo pubblico documentato

    if event_publisher is not None:
        if redis_url:
            from ...infrastructure.security.redis import (
                RedisRealtimePublisher,
                RedisRealtimeSubscriber,
            )

            publisher = RedisRealtimePublisher(redis_url, redis_prefix)
            event_publisher.register_consumer("realtime-publish", publisher.handle_outbox_event)
        else:
            event_publisher.register_consumer("realtime", notifier.handle_outbox_event)

        @bp.record_once
        def _start_outbox_dispatcher(state) -> None:
            runtime: dict[str, object] = {}

            @state.app.before_serving
            async def _bind_notifier_and_dispatch_outbox() -> None:
                notifier.bind_loop(asyncio.get_running_loop())

                subscriber = None
                if redis_url:
                    subscriber = RedisRealtimeSubscriber(
                        redis_url,
                        redis_prefix,
                        notifier.handle_outbox_event,
                    )
                    subscriber.start()
                    runtime["subscriber"] = subscriber

                async def dispatch_loop() -> None:
                    while True:
                        try:
                            await asyncio.to_thread(event_publisher.dispatch_consumer, "audit")
                            await asyncio.to_thread(
                                event_publisher.dispatch_consumer,
                                "realtime-publish" if redis_url else "realtime",
                            )
                        except Exception:
                            # Una caduta di connessione DB (es. MySQL riavviato
                            # durante il boot) non deve terminare il task: la
                            # CancelledError (BaseException) passa comunque per
                            # consentire lo shutdown pulito in after_serving.
                            _log.exception(
                                "Dispatch outbox fallito; riprovo al prossimo ciclo"
                            )
                        await asyncio.sleep(0.5)

                state.app.add_background_task(dispatch_loop)

            @state.app.after_serving
            async def _close_realtime_subscriber() -> None:
                subscriber = runtime.get("subscriber")
                if subscriber is not None:
                    subscriber.close()

    mission_handler = MissionRouteHandler(mission_svc)
    assignment_handler = AssignmentRouteHandler(
        assignment_svc, notifier, badge_svc, person_svc, mission_svc
    )
    objective_handler = ObjectiveRouteHandler(assignment_svc)
    activity_handler = ActivityRouteHandler(activity_svc, notifier, person_svc, badge_svc)
    person_handler = PersonRouteHandler(person_svc, badge_svc)
    group_handler = GroupRouteHandler(person_svc)
    acl_handler = AclRouteHandler(acl_svc, person_svc) if acl_svc is not None else None
    badge_handler = BadgeRouteHandler(badge_svc) if badge_svc is not None else None

    # ------------------------------------------------------------------
    # Route auth (opzionali)
    # ------------------------------------------------------------------
    if auth_service:
        register_web_auth_routes(
            bp,
            auth_service,
            auth_backend=auth_backend,
            oidc_redirect_uri=oidc_redirect_uri,
            person_svc=person_svc,
        )

    # ------------------------------------------------------------------
    # URL rules
    # ------------------------------------------------------------------
    bp.add_url_rule("/", view_func=mission_handler.list_missions, methods=["GET"])
    bp.add_url_rule("/missions", view_func=mission_handler.list_missions, methods=["GET"])
    bp.add_url_rule(
        "/missions/new",
        view_func=mission_handler.new_mission_form,
        endpoint="new_mission_form",
        methods=["GET"],
    )
    bp.add_url_rule("/missions/new", view_func=mission_handler.create_mission, methods=["POST"])
    bp.add_url_rule("/missions/<uuid:id>", view_func=mission_handler.get_mission, methods=["GET"])
    bp.add_url_rule(
        "/missions/<uuid:id>",
        view_func=mission_handler.delete_mission,
        endpoint="delete_mission",
        methods=["DELETE"],
    )
    # Nessuna route di aggiunta obiettivi: il blueprint è immutabile dopo la creazione.

    # Pagina dedicata alle assegnazioni (scorporata dalla missione): elenco delle
    # missioni assegnate, modulo di creazione e creazione vera e propria.
    bp.add_url_rule(
        "/assignments",
        view_func=assignment_handler.list_assignments_page,
        endpoint="list_assignments",
        methods=["GET"],
    )
    bp.add_url_rule(
        "/assignments/new",
        view_func=assignment_handler.new_assignment_form,
        endpoint="new_assignment_form",
        methods=["GET"],
    )
    bp.add_url_rule(
        "/assignments",
        view_func=assignment_handler.create_assignment_global,
        endpoint="create_assignment",
        methods=["POST"],
    )
    bp.add_url_rule(
        "/assignments/<uuid:id>",
        view_func=assignment_handler.get_assignment,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/assignments/<uuid:id>/assign",
        view_func=assignment_handler.assign_assignment,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/assignments/<uuid:id>/status",
        view_func=assignment_handler.update_assignment_status,
        methods=["PUT"],
    )
    bp.add_url_rule(
        "/assignments/<uuid:id>/badge",
        view_func=assignment_handler.award_badge,
        endpoint="award_assignment_badge",
        methods=["POST"],
    )
    bp.add_url_rule(
        "/assignments/<uuid:id>/objectives",
        view_func=objective_handler.list_objectives,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/activities/<uuid:id>",
        view_func=activity_handler.get_activity,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/activities/<uuid:id>/status",
        view_func=activity_handler.update_activity_status,
        methods=["PUT"],
    )
    bp.add_url_rule(
        "/activities/<uuid:id>/assign",
        view_func=activity_handler.assign_to_activity,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/activities/<uuid:id>/assign",
        view_func=activity_handler.unassign_from_activity,
        endpoint="unassign_from_activity",
        methods=["DELETE"],
    )
    bp.add_url_rule(
        "/activities/<uuid:id>/badge",
        view_func=activity_handler.award_badge,
        endpoint="award_activity_badge",
        methods=["POST"],
    )

    # ------------------------------------------------------------------
    # Persone
    # ------------------------------------------------------------------
    bp.add_url_rule("/persons", view_func=person_handler.list_persons, methods=["GET"])
    bp.add_url_rule(
        "/persons/new",
        view_func=person_handler.new_person_form,
        endpoint="new_person_form",
        methods=["GET"],
    )
    bp.add_url_rule("/persons/new", view_func=person_handler.create_person, methods=["POST"])
    bp.add_url_rule("/persons/<uuid:id>", view_func=person_handler.get_person, methods=["GET"])
    bp.add_url_rule(
        "/persons/<uuid:id>",
        view_func=person_handler.update_person,
        endpoint="update_person",
        methods=["PUT"],
    )
    bp.add_url_rule(
        "/persons/<uuid:id>",
        view_func=person_handler.delete_person,
        endpoint="delete_person",
        methods=["DELETE"],
    )

    # ------------------------------------------------------------------
    # Gruppi
    # ------------------------------------------------------------------
    bp.add_url_rule("/groups", view_func=group_handler.list_groups, methods=["GET"])
    bp.add_url_rule(
        "/groups/new",
        view_func=group_handler.new_group_form,
        endpoint="new_group_form",
        methods=["GET"],
    )
    bp.add_url_rule("/groups/new", view_func=group_handler.create_group, methods=["POST"])
    bp.add_url_rule("/groups/<uuid:id>", view_func=group_handler.get_group, methods=["GET"])
    bp.add_url_rule(
        "/groups/<uuid:id>",
        view_func=group_handler.update_group,
        endpoint="update_group",
        methods=["PUT"],
    )
    bp.add_url_rule(
        "/groups/<uuid:id>",
        view_func=group_handler.delete_group,
        endpoint="delete_group",
        methods=["DELETE"],
    )
    bp.add_url_rule(
        "/groups/<uuid:id>/members",
        view_func=group_handler.add_member,
        endpoint="add_group_member",
        methods=["POST"],
    )
    bp.add_url_rule(
        "/groups/<uuid:id>/members",
        view_func=group_handler.remove_member,
        endpoint="remove_group_member",
        methods=["DELETE"],
    )

    # ------------------------------------------------------------------
    # ACL (DESIGN §10): pagina unica di amministrazione — profili + entry.
    # ------------------------------------------------------------------
    if acl_handler is not None:
        bp.add_url_rule(
            "/acl",
            view_func=acl_handler.get_page,
            endpoint="acl_management",
            methods=["GET"],
        )
        bp.add_url_rule(
            "/acl/profile",
            view_func=acl_handler.set_profile,
            endpoint="set_acl_profile",
            methods=["POST"],
        )
        bp.add_url_rule(
            "/acl/profile/groups",
            view_func=acl_handler.remove_profile_group,
            endpoint="remove_acl_profile_group",
            methods=["DELETE"],
        )
        bp.add_url_rule(
            "/acl/entries",
            view_func=acl_handler.create_entry,
            endpoint="create_acl_entry",
            methods=["POST"],
        )
        bp.add_url_rule(
            "/acl/entries/<entry_id>",
            view_func=acl_handler.delete_entry,
            endpoint="delete_acl_entry",
            methods=["DELETE"],
        )

    # ------------------------------------------------------------------
    # Badge (solo se il servizio badge è disponibile)
    # ------------------------------------------------------------------
    if badge_handler is not None:
        bp.add_url_rule("/badges", view_func=badge_handler.list_badges, methods=["GET"])
        bp.add_url_rule(
            "/badges/new",
            view_func=badge_handler.new_badge_form,
            endpoint="new_badge_form",
            methods=["GET"],
        )
        bp.add_url_rule("/badges/new", view_func=badge_handler.create_badge, methods=["POST"])
        bp.add_url_rule("/badges/<uuid:id>", view_func=badge_handler.get_badge, methods=["GET"])

    if extension_registry is not None:
        for manifest in extension_registry.list():
            for index, route_spec in enumerate(manifest.provides_routes):
                bp.add_url_rule(
                    route_spec.path,
                    endpoint=f"extension_{manifest.id}_{index}",
                    view_func=_build_extension_view(manifest.id, extension_registry),
                    methods=[route_spec.method.upper()],
                )

    # ------------------------------------------------------------------
    # WebSocket real-time
    # Autenticazione gestita dall'handler stesso (non dal middleware ACL);
    # per questo /ws è nei percorsi pubblici del middleware.
    # ------------------------------------------------------------------
    @bp.websocket("/ws")
    async def ws():
        from quart import session as _session, websocket as ws_conn
        if not _session.get(WebOperatorIdentityAdapter.SESSION_KEY):
            await ws_conn.close(1008)
            return
        try:
            operator = await asyncio.to_thread(identity_provider.get_current_operator)
        except (AuthenticationError, ACLError):
            await ws_conn.close(1008)
            return
        allowed = await asyncio.to_thread(
            auth_policy.is_allowed, operator.id, Operation.VIEW, SYSTEM_RESOURCE
        )
        if not allowed:
            await ws_conn.close(1008)
            return
        conn = ws_conn._get_current_object()
        await notifier.connect(conn)
        try:
            while True:
                await ws_conn.receive()
        finally:
            await notifier.disconnect(conn)

    # ------------------------------------------------------------------
    # Middleware ACL (DESIGN §10): enforcement primario al confine. Ogni endpoint
    # è mappato su (Operation, ResourceRef); i service ricontrollano come difesa
    # in profondità usando il contesto operatore impostato dal middleware.
    # ------------------------------------------------------------------
    ACLMiddleware(
        bp,
        identity_provider,
        auth_policy,
        endpoint_acl=_WEB_ENDPOINT_ACL,
    )

    # ------------------------------------------------------------------
    # Mappatura eccezioni di dominio → JSON (vedi DESIGN §9.1)
    # I form di creazione inviano via fetch e si aspettano un corpo JSON
    # con il messaggio d'errore; senza questi handler una ValidationError
    # diventerebbe un 500 opaco.
    # ------------------------------------------------------------------
    @bp.errorhandler(ValidationError)
    async def _on_validation_error(exc):
        return jsonify({"error": exc.message}), 400

    @bp.errorhandler(NotFoundError)
    async def _on_not_found(exc):
        return jsonify({"error": exc.message}), 404

    @bp.errorhandler(ForbiddenError)
    async def _on_forbidden(exc):
        return jsonify({"error": exc.message}), 403

    @bp.errorhandler(StatusTransitionError)
    async def _on_status_transition(exc):
        return jsonify({"error": exc.message}), 409

    @bp.errorhandler(OperationAbortedError)
    async def _on_operation_aborted(exc):
        return jsonify({"error": exc.message}), 422

    # ------------------------------------------------------------------
    # Security headers su ogni risposta
    # ------------------------------------------------------------------
    @bp.after_request
    async def _add_security_headers(response):
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    return bp
