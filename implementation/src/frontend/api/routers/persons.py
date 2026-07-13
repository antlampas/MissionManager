# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
from uuid import UUID

from quart import jsonify, request
from quart.views import MethodView

from ....application.services.person_service import PersonService
from ..._http import operator_id, parse_json_body, run_blocking
from ..._utils import require_field


class PersonRouter(MethodView):
    def __init__(self, svc: PersonService, **kwargs) -> None:
        self._svc = svc

    # GET/POST /persons
    async def get(self, id: UUID = None):
        if id is not None:
            return jsonify(asdict(await run_blocking(
                self._svc.get, str(id), operator_id=operator_id()
            ))), 200
        persons = await run_blocking(
            self._svc.list, dict(request.args), operator_id=operator_id()
        )
        return jsonify([asdict(p) for p in persons]), 200

    async def post(self):
        # Il profilo ACL non si imposta alla creazione: una persona nasce con
        # il profilo meno privilegiato; l'assegnazione passa da PUT
        # /persons/<id>/acl (MANAGE_PROFILES, fuori dal catalogo delegabile).
        data = await parse_json_body()
        dto = await run_blocking(
            self._svc.add,
            nicknames=data.get("nicknames", []),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 201

    async def put(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.update,
            id=str(id),
            nicknames=data.get("nicknames"),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 200

    async def delete(self, id: UUID):
        await run_blocking(self._svc.remove, str(id), operator_id=operator_id())
        return "", 204


class GroupRouter(MethodView):
    def __init__(self, svc: PersonService, **kwargs) -> None:
        self._svc = svc

    async def get(self, id: UUID = None):
        if id is not None:
            group = await run_blocking(
                self._svc.get_group, str(id), operator_id=operator_id()
            )
            return jsonify(asdict(group)), 200
        groups = await run_blocking(self._svc.list_groups, operator_id=operator_id())
        return jsonify([asdict(g) for g in groups]), 200

    async def post(self):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.add_group,
            name=data.get("name"),
            zone_type=data.get("zone_type"),
            zone_description=data.get("zone_description"),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 201

    async def put(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(
            self._svc.update_group,
            group_id=str(id),
            name=data.get("name"),
            zone_type=data.get("zone_type"),
            zone_description=data.get("zone_description"),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 200

    async def delete(self, id: UUID):
        await run_blocking(self._svc.remove_group, str(id), operator_id=operator_id())
        return "", 204


class GroupMembersRouter(MethodView):
    def __init__(self, svc: PersonService, **kwargs) -> None:
        self._svc = svc

    async def get(self, id: UUID):
        persons = await run_blocking(
            self._svc.list_by_group, str(id), operator_id=operator_id()
        )
        return jsonify([asdict(p) for p in persons]), 200

    async def post(self, id: UUID):
        data = await parse_json_body()
        await run_blocking(
            self._svc.add_group_member,
            str(id),
            require_field(data, "person_id"),
            operator_id=operator_id(),
        )
        return "", 204

    async def delete(self, id: UUID):
        data = await parse_json_body()
        await run_blocking(
            self._svc.remove_group_member,
            str(id),
            require_field(data, "person_id"),
            operator_id=operator_id(),
        )
        return "", 204
