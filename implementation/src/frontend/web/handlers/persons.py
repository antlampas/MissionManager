# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
from typing import Optional
from uuid import UUID

from quart import jsonify, render_template

from ....application.services.badge_service import BadgeService
from ....application.services.person_service import PersonService
from ..._http import parse_json_body, run_blocking


class PersonRouteHandler:
    """Handler Quart per le pagine Web delle persone."""

    def __init__(
        self,
        svc: PersonService,
        badge_svc: Optional[BadgeService] = None,
    ) -> None:
        self._svc = svc
        self._badge_svc = badge_svc

    async def list_persons(self):
        persons = await run_blocking(self._svc.list, {})
        groups = await run_blocking(self._svc.list_groups)
        return await render_template("person_list.html", persons=persons, groups=groups)

    async def new_person_form(self):
        groups = await run_blocking(self._svc.list_groups)
        return await render_template("person_new.html", groups=groups)

    async def get_person(self, id: UUID):
        person = await run_blocking(self._svc.get, str(id))
        groups = await run_blocking(self._svc.list_groups)
        badges = (
            await run_blocking(self._badge_svc.list_by_person, str(id))
            if self._badge_svc
            else []
        )
        return await render_template(
            "person_detail.html", person=person, groups=groups, badges=badges
        )

    async def create_person(self):
        # Il profilo ACL non si imposta alla creazione: una persona nasce con
        # il profilo meno privilegiato; l'assegnazione avviene dalla pagina
        # /acl (MANAGE_PROFILES, fuori dal catalogo delegabile — DESIGN §10).
        data = await parse_json_body()
        dto = await run_blocking(self._svc.add, nicknames=data.get("nicknames", []))
        return jsonify(asdict(dto)), 201

    async def update_person(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(
            self._svc.update, id=str(id), nicknames=data.get("nicknames")
        )
        return jsonify(asdict(dto)), 200

    async def delete_person(self, id: UUID):
        await run_blocking(self._svc.remove, str(id))
        return "", 204
