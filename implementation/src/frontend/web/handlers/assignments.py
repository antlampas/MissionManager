# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
from typing import Optional
from uuid import UUID

from quart import jsonify, render_template

from ....application.services.assignment_service import AssignmentService
from ....application.services.badge_service import BadgeService
from ....application.services.mission_service import MissionService
from ....application.services.person_service import PersonService
from ..._http import operator_id, parse_json_body, run_blocking
from ..._utils import require_field
from ..notifier import RealtimeNotifier
from ._status import next_statuses

class AssignmentRouteHandler:
    """Handler Quart per le pagine Web degli assignment, con notifiche realtime.

    Possiede anche la pagina dedicata alle assegnazioni (``/assignments``):
    l'elenco delle missioni effettivamente assegnate e la creazione di nuove
    assegnazioni, scorporate dalla pagina di dettaglio della missione.
    """

    def __init__(
        self,
        svc: AssignmentService,
        notifier: RealtimeNotifier,
        badge_svc: Optional[BadgeService] = None,
        person_svc: Optional[PersonService] = None,
        mission_svc: Optional[MissionService] = None,
    ) -> None:
        self._svc = svc
        self._notifier = notifier
        self._badge_svc = badge_svc
        self._person_svc = person_svc
        self._mission_svc = mission_svc

    # ------------------------------------------------------------------
    # Pagina dedicata alle assegnazioni
    # ------------------------------------------------------------------

    async def list_assignments_page(self):
        """Elenco delle missioni *effettivamente assegnate* con le loro esecuzioni.

        Mostra solo le missioni che hanno almeno un ``MissionAssignment``; ogni
        voce di assegnazione linka al proprio dettaglio.
        """
        missions = await run_blocking(
            self._mission_svc.list, {}, operator_id=operator_id()
        ) if self._mission_svc else []
        persons = await run_blocking(self._person_svc.list, {}) if self._person_svc else []
        person_names = {p.id: p.primary_nickname for p in persons}

        assigned: list[dict] = []
        for mission in missions:
            assignments = await run_blocking(
                self._svc.list, mission.id, {}, operator_id=operator_id()
            )
            if assignments:
                assigned.append({"mission": mission, "assignments": assignments})

        return await render_template(
            "assignment_list.html",
            assigned=assigned,
            person_names=person_names,
        )

    async def new_assignment_form(self):
        """Modulo per creare una nuova assegnazione (scelta missione + assegnatario)."""
        missions = await run_blocking(
            self._mission_svc.list, {}, operator_id=operator_id()
        ) if self._mission_svc else []
        persons = await run_blocking(self._person_svc.list, {}) if self._person_svc else []
        groups = await run_blocking(self._person_svc.list_groups) if self._person_svc else []
        return await render_template(
            "assignment_new.html",
            missions=missions,
            persons=persons,
            groups=groups,
        )

    async def create_assignment_global(self):
        """Crea un'assegnazione: la missione arriva nel body (pagina dedicata)."""
        data = await parse_json_body()
        dto = await run_blocking(
            self._svc.create,
            mission_id=str(require_field(data, "mission_id")),
            assignee_type=data.get("assignee_type"),
            assignee_id=data.get("assignee_id"),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 201

    # ------------------------------------------------------------------
    # Dettaglio assegnazione
    # ------------------------------------------------------------------

    async def get_assignment(self, id: UUID):
        assignment = await run_blocking(self._svc.get, str(id), operator_id=operator_id())
        badges = await run_blocking(
            self._badge_svc.list, operator_id=operator_id()
        ) if self._badge_svc else []
        persons = await run_blocking(self._person_svc.list, {}) if self._person_svc else []
        groups = await run_blocking(self._person_svc.list_groups) if self._person_svc else []
        person_names = {p.id: p.primary_nickname for p in persons}
        group_names = {g.id: g.name for g in groups}

        # Candidati assegnabili per attività (perimetro DESIGN §2.4): la regola vive
        # nel layer applicativo; qui ci si limita a passarli al template.
        candidates_by_activity = await run_blocking(
            self._svc.list_activity_candidates, str(id)
        )

        return await render_template(
            "assignment_detail.html",
            assignment=assignment,
            badges=badges,
            persons=persons,
            groups=groups,
            person_names=person_names,
            group_names=group_names,
            candidates_by_activity=candidates_by_activity,
            allowed_statuses=next_statuses(assignment.status),
        )

    async def assign_assignment(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.assign,
            assignment_id=str(id),
            assignee_type=require_field(data, "assignee_type"),
            assignee_id=require_field(data, "assignee_id"),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 200

    async def update_assignment_status(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.update_status,
            str(id), require_field(data, "status"), operator_id=operator_id()
        )
        return jsonify(asdict(dto)), 200

    async def award_badge(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(self._badge_svc.award_to_assignment,
            badge_id=require_field(data, "badge_id"),
            assignment_id=str(id),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 201
