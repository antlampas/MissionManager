# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
from uuid import UUID

from quart import jsonify, request
from quart.views import MethodView

from ....application.services.assignment_service import AssignmentService
from ....application.services.badge_service import BadgeService
from ..._http import operator_id, parse_json_body, run_blocking
from ..._utils import require_field


class AssignmentRouter(MethodView):
    def __init__(self, svc: AssignmentService, badge_svc: BadgeService, **kwargs) -> None:
        self._svc = svc
        self._badge_svc = badge_svc

    # GET /missions/<id>/assignments[?status=...]  oppure  GET /assignments/<id>
    async def get(self, id: UUID = None, mission_id: UUID = None):
        if mission_id is not None:
            return jsonify(
                [asdict(a) for a in await run_blocking(
                    self._svc.list,
                    str(mission_id),
                    dict(request.args),
                    operator_id=operator_id(),
                )]
            ), 200
        return jsonify(asdict(await run_blocking(
            self._svc.get, str(id), operator_id=operator_id()
        ))), 200

    # POST /missions/<mission_id>/assignments  — crea assignment
    async def post(self, mission_id: UUID = None, id: UUID = None):
        data = await parse_json_body()

        if mission_id is not None:
            dto = await run_blocking(self._svc.create,
                mission_id=str(mission_id),
                assignee_type=data.get("assignee_type"),
                assignee_id=data.get("assignee_id"),
                operator_id=operator_id(),
            )
            return jsonify(asdict(dto)), 201

        # POST /assignments/<id>/assign
        dto = await run_blocking(
            self._svc.assign,
            assignment_id=str(id),
            assignee_type=require_field(data, "assignee_type"),
            assignee_id=require_field(data, "assignee_id"),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 200

    # PUT /assignments/<id>/status
    async def put(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.update_status,
            str(id), require_field(data, "status"), operator_id=operator_id()
        )
        return jsonify(asdict(dto)), 200


class AssignmentBadgeRouter(MethodView):
    """POST /assignments/<id>/badge — assegna un badge all'assignment."""

    def __init__(self, badge_svc: BadgeService, **kwargs) -> None:
        self._badge_svc = badge_svc

    async def post(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(self._badge_svc.award_to_assignment,
            badge_id=require_field(data, "badge_id"),
            assignment_id=str(id),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 201
