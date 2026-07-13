# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
from uuid import UUID

from quart import jsonify
from quart.views import MethodView

from ....application.services.assignment_service import AssignmentService
from ..._http import run_blocking


class ObjectiveRouter(MethodView):
    """GET /assignments/<id>/objectives — elenco obiettivi di un assignment."""

    def __init__(self, svc: AssignmentService, **kwargs) -> None:
        self._svc = svc

    async def get(self, id: UUID):
        dto = await run_blocking(self._svc.get, str(id))
        return jsonify([asdict(obj) for obj in dto.objectives]), 200
