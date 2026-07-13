# SPDX-License-Identifier: CC-BY-SA-4.0
from uuid import UUID

from quart import render_template

from ....application.services.assignment_service import AssignmentService
from ..._http import run_blocking


class ObjectiveRouteHandler:
    def __init__(self, svc: AssignmentService) -> None:
        self._svc = svc

    async def list_objectives(self, id: UUID):
        dto = await run_blocking(self._svc.get, str(id))
        return await render_template(
            "objectives.html",
            assignment_id=str(id),
            objectives=dto.objectives,
        )
