# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
from uuid import UUID

from quart import jsonify, request
from quart.views import MethodView

from ....application.services.mission_service import MissionService
from ..._http import operator_id, parse_json_body, run_blocking
from ..._utils import require_field


class MissionRouter(MethodView):
    def __init__(self, svc: MissionService, **kwargs) -> None:
        self._svc = svc

    async def get(self, id: UUID = None):
        if id is not None:
            return jsonify(asdict(await run_blocking(
                self._svc.get, str(id), operator_id=operator_id()
            ))), 200
        missions = await run_blocking(
            self._svc.list, dict(request.args), operator_id=operator_id()
        )
        return jsonify([asdict(m) for m in missions]), 200

    async def post(self):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.create,
            title=require_field(data, "title"),
            desc=data.get("description", ""),
            objectives=data.get("objectives", []),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 201

    async def delete(self, id: UUID):
        await run_blocking(self._svc.delete, str(id), operator_id=operator_id())
        return "", 204


class MissionObjectiveRouter(MethodView):
    """Route /missions/<id>/objectives — sola lettura.

    Il blueprint è immutabile dopo la creazione: gli obiettivi (e le loro attività)
    si definiscono solo in fase di creazione della missione, quindi questa route
    espone unicamente l'elenco in lettura.
    """

    def __init__(self, svc: MissionService, **kwargs) -> None:
        self._svc = svc

    async def get(self, id: UUID):
        dto = await run_blocking(self._svc.get, str(id), operator_id=operator_id())
        return jsonify([asdict(obj) for obj in dto.objectives]), 200
