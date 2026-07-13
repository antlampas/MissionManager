# SPDX-License-Identifier: CC-BY-SA-4.0
"""Estensione di esempio: statistiche aggregate su una missione."""
from __future__ import annotations

from dataclasses import dataclass

from src.domain.extensions import ExtensionManifest, ExtensionRequest, ExtensionResult


@dataclass
class _Stats:
    mission_id: str
    total_assignments: int
    completed: int
    in_progress: int
    failed: int
    unassigned: int


class Extension:
    def __init__(
        self,
        manifest: ExtensionManifest,
        mission_svc=None,
        assignment_svc=None,
        **_kwargs,
    ) -> None:
        self.manifest = manifest
        self._mission_svc = mission_svc
        self._assignment_svc = assignment_svc

    def execute(self, request: ExtensionRequest) -> ExtensionResult:
        mission_id = request.params.get("mission_id")
        if not mission_id:
            return ExtensionResult(
                data={"error": "mission_id richiesto"},
                status_code=400,
            )

        if self._mission_svc is None or self._assignment_svc is None:
            return ExtensionResult(
                data={"error": "Servizi non configurati"},
                status_code=500,
            )

        try:
            self._mission_svc.get(mission_id)
        except Exception as exc:
            return ExtensionResult(data={"error": str(exc)}, status_code=404)

        assignments = self._assignment_svc.list(mission_id, {})
        stats = _Stats(
            mission_id=mission_id,
            total_assignments=len(assignments),
            completed=sum(1 for a in assignments if a.status == "COMPLETED"),
            in_progress=sum(1 for a in assignments if a.status == "IN_PROGRESS"),
            failed=sum(1 for a in assignments if a.status == "FAILED"),
            unassigned=sum(1 for a in assignments if a.status in ("UNASSIGNED", "ASSIGNED")),
        )
        return ExtensionResult(
            data={
                "mission_id": stats.mission_id,
                "total_assignments": stats.total_assignments,
                "completed": stats.completed,
                "in_progress": stats.in_progress,
                "failed": stats.failed,
                "pending": stats.unassigned,
            },
            status_code=200,
        )
