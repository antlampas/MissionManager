# SPDX-License-Identifier: CC-BY-SA-4.0
"""Plugin di esempio: validazione extra prima di un cambio di stato.

Dimostra un plugin BEFORE_ hook TRUSTED che può impostare abort=True per
bloccare operazioni non consentite secondo regole business custom.

Regola di esempio: un assignment non può passare a COMPLETED se ha attività
in stato diverso da COMPLETED o FAILED (rilevato tramite il payload).
"""
from __future__ import annotations

import logging

from src.application.plugin_registry import HookContext
from src.domain.plugins import HookPoint, PluginManifest, PluginTrustLevel

logger = logging.getLogger(__name__)


class Plugin:
    manifest = PluginManifest(
        id="status-validator",
        name="status_validator",
        version="1.0.0",
        description="Blocca transizioni di stato non consentite per regole business custom",
        hooks=[HookPoint.BEFORE_UPDATE_STATUS],
        trust_level=PluginTrustLevel.TRUSTED,
        priority=50,
    )

    def execute(self, context: HookContext) -> None:
        new_status = context.payload.get("new_status", "")
        entity_type = context.payload.get("entity_type", "")

        if entity_type == "ASSIGNMENT" and new_status == "COMPLETED":
            open_activities = context.payload.get("open_activities_count", 0)
            if open_activities > 0:
                context.abort = True
                context.abort_reason = (
                    f"L'assignment ha ancora {open_activities} attività non completate"
                )
                logger.warning(
                    "[status_validator] Transizione COMPLETED bloccata: %d attività aperte",
                    open_activities,
                )
