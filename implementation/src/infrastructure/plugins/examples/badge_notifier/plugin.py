# SPDX-License-Identifier: CC-BY-SA-4.0
"""Plugin di esempio: notifica post-assegnazione badge.

Dimostra un plugin AFTER_ hook TRUSTED che legge il risultato dell'operazione
dal contesto per inviare una notifica (qui simulata con un log strutturato).
"""
from __future__ import annotations

import logging

from src.application.plugin_registry import HookContext
from src.domain.plugins import HookPoint, PluginManifest, PluginTrustLevel

logger = logging.getLogger(__name__)


class Plugin:
    manifest = PluginManifest(
        id="badge-notifier",
        name="badge_notifier",
        version="1.0.0",
        description="Logga i dettagli del badge assegnato dopo ogni award",
        hooks=[HookPoint.AFTER_AWARD_BADGE],
        trust_level=PluginTrustLevel.TRUSTED,
        priority=10,
    )

    def execute(self, context: HookContext) -> None:
        badge_id = context.payload.get("badge_id", "?")
        target_type = context.payload.get("target_type", "?")
        target_id = context.payload.get("target_id", "?")

        award = context.result
        recipients_count = 0
        if award is not None and hasattr(award, "recipients"):
            recipients_count = len(award.recipients)

        logger.info(
            "[badge_notifier] Badge %s assegnato a %s/%s — %d destinatari (operator=%s)",
            badge_id, target_type, target_id, recipients_count, context.operator_id,
        )
