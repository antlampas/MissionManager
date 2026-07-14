# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
import asyncio
from typing import Any, Optional

from quart import Blueprint, Quart, jsonify, request

from ...domain.extensions import ExtensionRequest
from ...domain.identity import OperatorIdentityProvider
from ...application.services.acl_service import AclService
from ...application.services.activity_service import ActivityService
from ...application.services.assignment_service import AssignmentService
from ...application.services.auth_service import AuthService
from ...application.authorization import AuthorizationPolicy
from ...application.services.badge_service import BadgeService
from ...application.extension_registry import ExtensionRegistry
from ...application.services.mission_service import MissionService
from ...application.services.person_service import PersonService
from .error_handler import ErrorHandler
from .middleware import AuthMiddleware
from .routers.acl import AclEntriesRouter, AclEntryRouter, PersonAclRouter
from .routers.activities import ActivityRouter, ObjectiveActivitiesRouter
from .routers.assignments import AssignmentBadgeRouter, AssignmentRouter
from .routers.auth import register_auth_routes
from .routers.badges import BadgeRouter, PersonBadgesRouter
from .routers.missions import MissionObjectiveRouter, MissionRouter
from .routers.objectives import ObjectiveRouter
from .routers.persons import GroupMembersRouter, GroupRouter, PersonRouter


def build_extension_view(ext_id: str, route_spec: Any, extension_registry: ExtensionRegistry, identity_provider: OperatorIdentityProvider):
    async def extension_view(**kwargs):
        from quart import g

        from ...domain.exceptions import ValidationError

        operator = getattr(g, "operator", None)
        op_id = operator.id if operator else None
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
            ExtensionRequest(operator_id=op_id, params=params, body=params),
        )
        return jsonify({"data": result.data, "message": result.message}), result.status_code

    # Il nome include il metodo HTTP: due route con la stessa path e metodi
    # diversi devono produrre endpoint Quart distinti.
    safe_path = route_spec.path.replace('/', '_').strip('_')
    extension_view.__name__ = f"ext_{route_spec.method.upper()}_{safe_path}"
    return extension_view


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'none'",
}


class RestApp:
    """Bootstrap del frontend REST API (Quart, route sotto /api)."""

    def __init__(
        self,
        mission_svc: MissionService,
        assignment_svc: AssignmentService,
        activity_svc: ActivityService,
        badge_svc: BadgeService,
        person_svc: PersonService,
        acl_svc: AclService,
        extension_registry: ExtensionRegistry,
        identity_provider: OperatorIdentityProvider,
        auth_policy: AuthorizationPolicy,
        auth_service: Optional[AuthService] = None,
        secret_key: Optional[str] = None,
        rate_limit_policy=None,
        event_publisher=None,
    ) -> None:
        self.app = Quart(__name__)

        if secret_key:
            self.app.secret_key = secret_key

        self._mission_svc = mission_svc
        self._assignment_svc = assignment_svc
        self._activity_svc = activity_svc
        self._badge_svc = badge_svc
        self._person_svc = person_svc
        self._acl_svc = acl_svc
        self._extension_registry = extension_registry
        self._identity_provider = identity_provider
        self._auth_policy = auth_policy
        self._event_publisher = event_publisher

        ErrorHandler.register(self.app)
        self._register_routes(auth_service)
        AuthMiddleware(
            self.app,
            identity_provider,
            auth_policy,
            rate_limit_policy=rate_limit_policy,
        )

        @self.app.after_request
        async def add_security_headers(response):
            for header, value in _SECURITY_HEADERS.items():
                response.headers.setdefault(header, value)
            return response

        @self.app.after_request
        async def dispatch_outbox(response):
            if self._event_publisher is not None:
                await asyncio.to_thread(self._event_publisher.dispatch_consumer, "audit")
            return response

    def _register_routes(self, auth_service: Optional[AuthService]) -> None:
        api = Blueprint("api", __name__, url_prefix="/api")

        # --- Auth (pubblico: gestito prima del middleware ACL) ---
        if auth_service:
            self.app.register_blueprint(
                register_auth_routes(auth_service, self._auth_policy)
            )

        # --- Missions ---
        mission_view = MissionRouter.as_view("missions", svc=self._mission_svc)
        api.add_url_rule("/missions", view_func=mission_view, methods=["GET", "POST"])
        api.add_url_rule("/missions/<uuid:id>", view_func=mission_view, methods=["GET", "DELETE"])
        obj_view = MissionObjectiveRouter.as_view("mission_objectives", svc=self._mission_svc)
        # Sola lettura: il blueprint è immutabile dopo la creazione (niente POST).
        api.add_url_rule("/missions/<uuid:id>/objectives", view_func=obj_view, methods=["GET"])

        # --- Assignments ---
        asgn_list_view = AssignmentRouter.as_view(
            "mission_assignments", svc=self._assignment_svc, badge_svc=self._badge_svc
        )
        api.add_url_rule(
            "/missions/<uuid:mission_id>/assignments",
            view_func=asgn_list_view,
            methods=["GET", "POST"],
        )
        asgn_view = AssignmentRouter.as_view(
            "assignments", svc=self._assignment_svc, badge_svc=self._badge_svc
        )
        api.add_url_rule("/assignments/<uuid:id>", view_func=asgn_view, methods=["GET"])
        api.add_url_rule("/assignments/<uuid:id>/assign", view_func=asgn_view, methods=["POST"])
        api.add_url_rule("/assignments/<uuid:id>/status", view_func=asgn_view, methods=["PUT"])
        asgn_badge_view = AssignmentBadgeRouter.as_view("assignment_badge", badge_svc=self._badge_svc)
        api.add_url_rule("/assignments/<uuid:id>/badge", view_func=asgn_badge_view, methods=["POST"])
        obj_asgn_view = ObjectiveRouter.as_view("assignment_objectives", svc=self._assignment_svc)
        api.add_url_rule("/assignments/<uuid:id>/objectives", view_func=obj_asgn_view, methods=["GET"])

        # --- Activities ---
        act_view = ActivityRouter.as_view("activities", svc=self._activity_svc, badge_svc=self._badge_svc)
        api.add_url_rule("/activities/<uuid:id>", view_func=act_view, methods=["GET"])
        api.add_url_rule("/activities/<uuid:id>/status", view_func=act_view, methods=["PUT"])
        api.add_url_rule("/activities/<uuid:id>/assign", view_func=act_view, methods=["POST", "DELETE"])
        api.add_url_rule("/activities/<uuid:id>/badge", view_func=act_view, methods=["POST"])

        obj_act_view = ObjectiveActivitiesRouter.as_view("objective_activities", svc=self._activity_svc)
        api.add_url_rule("/objectives/<uuid:id>/activities", view_func=obj_act_view, methods=["GET"])

        # --- Badges ---
        badge_view = BadgeRouter.as_view("badges", svc=self._badge_svc)
        api.add_url_rule("/badges", view_func=badge_view, methods=["GET", "POST"])
        api.add_url_rule("/badges/<uuid:id>", view_func=badge_view, methods=["GET"])

        person_badge_view = PersonBadgesRouter.as_view("person_badges", svc=self._badge_svc)
        api.add_url_rule("/persons/<uuid:id>/badges", view_func=person_badge_view, methods=["GET"])

        # --- ACL (DESIGN §10): entry + profili ---
        acl_entries_view = AclEntriesRouter.as_view("acl_entries", svc=self._acl_svc)
        api.add_url_rule("/acl/entries", view_func=acl_entries_view, methods=["GET", "POST"])
        acl_entry_view = AclEntryRouter.as_view("acl_entry", svc=self._acl_svc)
        api.add_url_rule(
            "/acl/entries/<entry_id>",
            view_func=acl_entry_view,
            methods=["PATCH", "DELETE"],
        )
        person_acl_view = PersonAclRouter.as_view("person_acl", svc=self._person_svc)
        api.add_url_rule("/persons/<uuid:id>/acl", view_func=person_acl_view, methods=["PUT"])

        # --- Persons & Groups ---
        person_view = PersonRouter.as_view("persons", svc=self._person_svc)
        api.add_url_rule("/persons", view_func=person_view, methods=["GET", "POST"])
        api.add_url_rule("/persons/<uuid:id>", view_func=person_view, methods=["GET", "PUT", "DELETE"])

        group_view = GroupRouter.as_view("groups", svc=self._person_svc)
        api.add_url_rule("/groups", view_func=group_view, methods=["GET", "POST"])
        api.add_url_rule(
            "/groups/<uuid:id>",
            view_func=group_view,
            methods=["GET", "PUT", "DELETE"],
        )
        members_view = GroupMembersRouter.as_view("group_members", svc=self._person_svc)
        api.add_url_rule(
            "/groups/<uuid:id>/members",
            view_func=members_view,
            methods=["GET", "POST", "DELETE"],
        )

        # --- Estensioni (dinamiche) ---
        for manifest in self._extension_registry.list():
            for route_spec in manifest.provides_routes:
                api.add_url_rule(
                    route_spec.path,
                    view_func=build_extension_view(
                        manifest.id, route_spec, self._extension_registry, self._identity_provider
                    ),
                    methods=[route_spec.method],
                )

        self.app.register_blueprint(api)

    def run(self, host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> None:
        self.app.run(host=host, port=port, debug=debug)
