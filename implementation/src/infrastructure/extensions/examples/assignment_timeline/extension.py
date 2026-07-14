# SPDX-License-Identifier: CC-BY-SA-4.0
"""Estensione di esempio: timeline degli assignment di una missione.

Scatena gli hook custom ``BEFORE_EXT:assignment-timeline:timeline`` (con
possibilità di veto) e ``AFTER_EXT:assignment-timeline:timeline``.
"""
from __future__ import annotations

from src.domain.extensions import ExtensionManifest, ExtensionRequest, ExtensionResult

_STATUS_ORDER = {
    "IN_PROGRESS": 0,
    "ASSIGNED": 1,
    "UNASSIGNED": 2,
    "COMPLETED": 3,
    "FAILED": 4,
}


class Extension:
    def __init__(
        self,
        manifest: ExtensionManifest,
        assignment_svc=None,
        hook_emitter=None,
        **_kwargs,
    ) -> None:
        self.manifest = manifest
        self._assignment_svc = assignment_svc
        self._hooks = hook_emitter

    def execute(self, request: ExtensionRequest) -> ExtensionResult:
        mission_id = request.params.get("mission_id")
        if not mission_id:
            return ExtensionResult(data={"error": "mission_id richiesto"}, status_code=400)

        if self._assignment_svc is None:
            return ExtensionResult(
                data={"error": "AssignmentService non configurato"}, status_code=500
            )

        if self._hooks is not None:
            self._hooks.fire_before(
                "timeline", {"mission_id": mission_id}, operator_id=request.operator_id
            )

        try:
            assignments = self._assignment_svc.list(mission_id, {})
        except Exception as exc:
            return ExtensionResult(data={"error": str(exc)}, status_code=404)

        sorted_assignments = sorted(
            assignments,
            key=lambda a: _STATUS_ORDER.get(a.status, 99),
        )

        timeline = [
            {
                "assignment_id": str(a.id),
                "status": a.status,
                "assignee_type": a.assignee_type,
                "assignee_id": str(a.assignee_id) if a.assignee_id else None,
                "objectives_count": len(a.objectives),
            }
            for a in sorted_assignments
        ]

        data = {
            "mission_id": mission_id,
            "timeline": timeline,
            "total": len(timeline),
        }
        if self._hooks is not None:
            self._hooks.fire_after(
                "timeline",
                {"mission_id": mission_id},
                result=data,
                operator_id=request.operator_id,
            )
        return ExtensionResult(data=data, status_code=200)
