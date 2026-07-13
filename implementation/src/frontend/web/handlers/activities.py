# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict
from typing import Optional
from uuid import UUID

from quart import jsonify, render_template

from ....application.services.activity_service import ActivityService
from ....application.services.badge_service import BadgeService
from ....application.services.person_service import PersonService
from ..._http import operator_id, parse_json_body, run_blocking
from ..._utils import require_field
from ..notifier import RealtimeNotifier
from ._status import next_statuses

class ActivityRouteHandler:
    """Handler Quart per le pagine Web delle attività, con notifiche realtime."""

    def __init__(
        self,
        svc: ActivityService,
        notifier: RealtimeNotifier,
        person_svc: Optional[PersonService] = None,
        badge_svc: Optional[BadgeService] = None,
    ) -> None:
        self._svc = svc
        self._notifier = notifier
        self._person_svc = person_svc
        self._badge_svc = badge_svc

    async def get_activity(self, id: UUID):
        activity = await run_blocking(self._svc.get, str(id), operator_id=operator_id())
        persons = await run_blocking(self._person_svc.list, {}) if self._person_svc else []
        badges = await run_blocking(
            self._badge_svc.list, operator_id=operator_id()
        ) if self._badge_svc else []
        person_names = {p.id: p.primary_nickname for p in persons}
        # Persone assegnabili: quelle non ancora assegnate a questa attività.
        candidates = [p for p in persons if p.id not in set(activity.assignees)]
        return await render_template(
            "activity_detail.html",
            activity=activity,
            persons=persons,
            candidates=candidates,
            person_names=person_names,
            badges=badges,
            allowed_statuses=next_statuses(activity.status),
        )

    async def update_activity_status(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.update_status,
            str(id),
            require_field(data, "status"),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 200

    async def assign_to_activity(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.assign_to,
            str(id), require_field(data, "person_id"), operator_id=operator_id()
        )
        return jsonify(asdict(dto)), 200

    async def unassign_from_activity(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(self._svc.unassign,
            str(id), require_field(data, "person_id"), operator_id=operator_id()
        )
        return jsonify(asdict(dto)), 200

    async def award_badge(self, id: UUID):
        data = await parse_json_body()
        dto = await run_blocking(self._badge_svc.award_to_activity,
            badge_id=require_field(data, "badge_id"),
            activity_id=str(id),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 201
