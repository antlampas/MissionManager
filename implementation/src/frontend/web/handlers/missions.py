# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
from uuid import UUID

from quart import jsonify, render_template

from ....application.services.mission_service import MissionService
from ..._http import operator_id, parse_json_body, run_blocking

class MissionRouteHandler:
    """Handler Quart per le pagine Web delle missioni (solo blueprint).

    L'assegnazione a persone/gruppi è stata scorporata nella pagina dedicata
    ``/assignments`` (vedi :class:`AssignmentRouteHandler`): la pagina di
    dettaglio/modifica della missione mostra ora soltanto il blueprint
    (obiettivi e attività).
    """

    def __init__(self, svc: MissionService) -> None:
        self._svc = svc

    async def list_missions(self):
        missions = await run_blocking(self._svc.list, {}, operator_id=operator_id())
        return await render_template("mission_list.html", missions=missions)

    async def new_mission_form(self):
        return await render_template("mission_new.html")

    async def get_mission(self, id: UUID):
        mission = await run_blocking(self._svc.get, str(id), operator_id=operator_id())
        return await render_template("mission_detail.html", mission=mission)

    async def delete_mission(self, id: UUID):
        await run_blocking(self._svc.delete, str(id), operator_id=operator_id())
        return "", 204

    async def create_mission(self):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.create,
            title=data.get("title", ""),
            desc=data.get("description", ""),
            objectives=data.get("objectives", []),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 201

    # Nessun add_objective: il blueprint è immutabile dopo la creazione. Obiettivi
    # e attività si definiscono solo nel form di creazione (vedi DESIGN §2.4).
