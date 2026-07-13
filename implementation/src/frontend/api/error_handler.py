# SPDX-License-Identifier: CC-BY-SA-4.0
from quart import Quart, jsonify

from ...domain.exceptions import (
    ACLError,
    AuthenticationError,
    AuthorizationError,
    ForbiddenError,
    MissionManagerError,
    NotFoundError,
    OperationAbortedError,
    RateLimitExceededError,
    StatusTransitionError,
    ValidationError,
)

_WWW_AUTH = 'Bearer realm="missionmanager"'


class ErrorHandler:
    """Mappa le eccezioni di dominio ai codici HTTP e al formato JSON."""

    @staticmethod
    def register(app: Quart) -> None:
        @app.errorhandler(ValidationError)
        async def handle_validation(exc: ValidationError):
            body = {"error": exc.message}
            if exc.field:
                body["field"] = exc.field
            return jsonify(body), 400

        @app.errorhandler(NotFoundError)
        async def handle_not_found(exc: NotFoundError):
            body = {"error": exc.message}
            if exc.resource_type:
                body["resource_type"] = exc.resource_type
            if exc.resource_id:
                body["resource_id"] = str(exc.resource_id)
            return jsonify(body), 404

        @app.errorhandler(AuthenticationError)
        async def handle_authentication(exc: AuthenticationError):
            return (
                jsonify({"error": exc.message}),
                401,
                {"WWW-Authenticate": _WWW_AUTH},
            )

        @app.errorhandler(AuthorizationError)
        async def handle_authorization(exc: AuthorizationError):
            return jsonify({"error": exc.message}), 403

        @app.errorhandler(ForbiddenError)
        async def handle_forbidden(exc: ForbiddenError):
            return jsonify({"error": exc.message}), 403

        @app.errorhandler(ACLError)
        async def handle_acl(exc: ACLError):
            return jsonify({"error": exc.message}), 403

        @app.errorhandler(StatusTransitionError)
        async def handle_status_transition(exc: StatusTransitionError):
            return jsonify(
                {
                    "error": exc.message,
                    "current": exc.current_status,
                    "requested": exc.requested_status,
                }
            ), 409

        @app.errorhandler(OperationAbortedError)
        async def handle_aborted(exc: OperationAbortedError):
            return jsonify({"error": exc.message}), 422

        @app.errorhandler(RateLimitExceededError)
        async def handle_rate_limit(exc: RateLimitExceededError):
            body = {"error": exc.message}
            if exc.limit is not None:
                body["limit"] = exc.limit
            if exc.window is not None:
                body["window"] = exc.window
            return jsonify(body), 429

        @app.errorhandler(MissionManagerError)
        async def handle_domain(exc: MissionManagerError):
            return jsonify({"error": exc.message}), 500

        @app.errorhandler(KeyError)
        async def handle_key_error(exc: KeyError):
            return jsonify({"error": f"Campo obbligatorio mancante nel body: {exc}"}), 400

        @app.errorhandler(Exception)
        async def handle_unexpected(exc: Exception):
            app.logger.exception("Errore non gestito")
            return jsonify({"error": "Errore interno"}), 500
