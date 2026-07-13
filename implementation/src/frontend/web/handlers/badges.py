# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
from uuid import UUID

from quart import jsonify, render_template

from ....application.services.badge_service import BadgeService
from ..._http import operator_id, parse_json_body, run_blocking


class BadgeRouteHandler:
    """Handler Quart per le pagine Web del catalogo badge."""

    def __init__(self, svc: BadgeService) -> None:
        self._svc = svc

    async def list_badges(self):
        badges = await run_blocking(self._svc.list, operator_id=operator_id())
        return await render_template("badge_list.html", badges=badges)

    async def new_badge_form(self):
        return await render_template("badge_new.html")

    async def get_badge(self, id: UUID):
        badge = await run_blocking(self._svc.get, str(id), operator_id=operator_id())
        return await render_template("badge_detail.html", badge=badge)

    async def create_badge(self):
        data = await parse_json_body()
        dto = await run_blocking(
            self._svc.create,
            name=data.get("name", ""),
            desc=data.get("description", ""),
            image_url=data.get("image_url") or None,
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 201
