# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
from uuid import UUID

from quart import jsonify
from quart.views import MethodView

from ....application.services.badge_service import BadgeService
from ..._http import operator_id, parse_json_body, run_blocking
from ..._utils import require_field


class BadgeRouter(MethodView):
    def __init__(self, svc: BadgeService, **kwargs) -> None:
        self._svc = svc

    async def get(self, id: UUID = None):
        if id is not None:
            return jsonify(asdict(await run_blocking(
                self._svc.get, str(id), operator_id=operator_id()
            ))), 200
        return jsonify([asdict(b) for b in await run_blocking(
            self._svc.list, operator_id=operator_id()
        )]), 200

    async def post(self):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.create,
            name=require_field(data, "name"),
            desc=data.get("description", ""),
            image_url=data.get("image_url"),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 201

class PersonBadgesRouter(MethodView):
    def __init__(self, svc: BadgeService, **kwargs) -> None:
        self._svc = svc

    async def get(self, id: UUID):
        badges = await run_blocking(
            self._svc.list_by_person, str(id), operator_id=operator_id()
        )
        return jsonify([asdict(b) for b in badges]), 200
