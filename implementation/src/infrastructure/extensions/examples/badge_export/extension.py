# SPDX-License-Identifier: CC-BY-SA-4.0
"""Estensione di esempio: esportazione badge di una persona in JSON."""
from __future__ import annotations

from src.domain.extensions import ExtensionManifest, ExtensionRequest, ExtensionResult


class Extension:
    def __init__(
        self,
        manifest: ExtensionManifest,
        badge_svc=None,
        person_svc=None,
        **_kwargs,
    ) -> None:
        self.manifest = manifest
        self._badge_svc = badge_svc
        self._person_svc = person_svc

    def execute(self, request: ExtensionRequest) -> ExtensionResult:
        person_id = request.params.get("person_id")
        if not person_id:
            return ExtensionResult(data={"error": "person_id richiesto"}, status_code=400)

        if self._badge_svc is None:
            return ExtensionResult(data={"error": "BadgeService non configurato"}, status_code=500)

        try:
            awards = self._badge_svc.list_by_person(person_id)
        except Exception as exc:
            return ExtensionResult(data={"error": str(exc)}, status_code=404)

        data = [
            {
                "badge_id": str(a.badge.id),
                "badge_name": a.badge.name,
                "target_type": a.target_type,
                "target_id": str(a.target_id),
                "awarded_at": str(a.awarded_at),
            }
            for a in awards
        ]
        return ExtensionResult(
            data={"person_id": person_id, "badges": data, "count": len(data)},
            status_code=200,
        )
