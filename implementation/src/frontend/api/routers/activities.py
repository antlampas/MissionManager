# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
from uuid import UUID

from quart import jsonify, request
from quart.views import MethodView

from ....application.services.activity_service import ActivityService
from ....application.services.badge_service import BadgeService
from ..._http import operator_id, parse_json_body, run_blocking
from ..._utils import require_field


class ActivityRouter(MethodView):
    def __init__(self, svc: ActivityService, badge_svc: BadgeService, **kwargs) -> None:
        self._svc = svc
        self._badge_svc = badge_svc

    # GET /activities/<id>
    async def get(self, id: UUID):
        return jsonify(asdict(await run_blocking(
            self._svc.get, str(id), operator_id=operator_id()
        ))), 200

    # POST /activities/<id>/assign  oppure  /activities/<id>/badge
    async def post(self, id: UUID):
        data = await parse_json_body()
        if request.path.rstrip("/").endswith("/badge"):
            dto = await run_blocking(self._badge_svc.award_to_activity,
                badge_id=require_field(data, "badge_id"),
                activity_id=str(id),
                operator_id=operator_id(),
            )
            return jsonify(asdict(dto)), 201
        # default: assign
        dto = await run_blocking(self._svc.assign_to,
            str(id), require_field(data, "person_id"), operator_id=operator_id()
        )
        return jsonify(asdict(dto)), 200

    # PUT /activities/<id>/status
    async def put(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.update_status,
            str(id),
            require_field(data, "status"),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 200

    # DELETE /activities/<id>/assign  (rimuovi assegnatario)
    async def delete(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.unassign,
            str(id), require_field(data, "person_id"), operator_id=operator_id()
        )
        return jsonify(asdict(dto)), 200

class ObjectiveActivitiesRouter(MethodView):
    def __init__(self, svc: ActivityService, **kwargs) -> None:
        self._svc = svc

    async def get(self, id: UUID):
        activities = await run_blocking(
            self._svc.list_by_objective, str(id), operator_id=operator_id()
        )
        return jsonify([asdict(act) for act in activities]), 200
