# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
from uuid import UUID

from quart import jsonify, render_template

from ....application.services.person_service import PersonService
from ..._http import parse_json_body, run_blocking
from ..._utils import require_field


class GroupRouteHandler:
    """Handler Quart per le pagine Web dei gruppi e dei loro membri."""

    def __init__(self, svc: PersonService) -> None:
        self._svc = svc

    async def list_groups(self):
        groups = await run_blocking(self._svc.list_groups)
        return await render_template("group_list.html", groups=groups)

    async def new_group_form(self):
        return await render_template("group_new.html")

    async def get_group(self, id: UUID):
        group = await run_blocking(self._svc.get_group, str(id))
        members = await run_blocking(self._svc.list_by_group, str(id))
        all_persons = await run_blocking(self._svc.list, {})
        member_ids = {m.id for m in members}
        candidates = [p for p in all_persons if p.id not in member_ids]
        return await render_template(
            "group_detail.html", group=group, members=members, candidates=candidates
        )

    async def create_group(self):
        data = await parse_json_body()
        dto = await run_blocking(
            self._svc.add_group,
            name=data.get("name", ""),
            zone_type=data.get("zone_type"),
            zone_description=data.get("zone_description"),
        )
        return jsonify(asdict(dto)), 201

    async def update_group(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(
            self._svc.update_group,
            group_id=str(id),
            name=data.get("name"),
            zone_type=data.get("zone_type"),
            zone_description=data.get("zone_description"),
        )
        return jsonify(asdict(dto)), 200

    async def delete_group(self, id: UUID):
        await run_blocking(self._svc.remove_group, str(id))
        return "", 204

    async def add_member(self, id: UUID):
        data = await parse_json_body()
        await run_blocking(
            self._svc.add_group_member, str(id), require_field(data, "person_id")
        )
        return "", 204

    async def remove_member(self, id: UUID):
        data = await parse_json_body()
        await run_blocking(
            self._svc.remove_group_member, str(id), require_field(data, "person_id")
        )
        return "", 204
