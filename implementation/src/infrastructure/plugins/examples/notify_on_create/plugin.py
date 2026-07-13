# SPDX-License-Identifier: CC-BY-SA-4.0
"""Plugin di esempio: notifica (log) alla creazione di una missione o assignment.

Dimostra un plugin AFTER_ hook SANDBOXED che non ha bisogno di mutare il
contesto e non richiede accesso privilegiato all'applicazione.
"""
from __future__ import annotations

import logging

from src.application.plugin_registry import HookContext
from src.domain.plugins import HookPoint, MissionHook, PluginManifest, PluginTrustLevel

logger = logging.getLogger(__name__)


class Plugin:
    manifest = PluginManifest(
        id="notify-on-create",
        name="notify_on_create",
        version="1.0.0",
        description="Logga un messaggio alla creazione di missioni e assignment",
        hooks=[HookPoint.AFTER_CREATE_MISSION, HookPoint.AFTER_CREATE_ASSIGNMENT],
        trust_level=PluginTrustLevel.SANDBOXED,
        priority=0,
    )

    def execute(self, context: HookContext) -> None:
        if context.hook_point == HookPoint.AFTER_CREATE_MISSION:
            title = context.payload.get("title", "?")
            logger.info(
                "[notify_on_create] Nuova missione creata: %r (operator=%s)",
                title, context.operator_id,
            )
        elif context.hook_point == HookPoint.AFTER_CREATE_ASSIGNMENT:
            mission_id = context.payload.get("mission_id", "?")
            assignee = context.payload.get("assignee_id", "non assegnato")
            logger.info(
                "[notify_on_create] Nuovo assignment su missione %s (assegnatario=%s, operator=%s)",
                mission_id, assignee, context.operator_id,
            )
