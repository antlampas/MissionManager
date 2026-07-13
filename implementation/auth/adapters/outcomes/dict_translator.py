# SPDX-License-Identifier: CC-BY-SA-4.0
"""Simple transport-neutral outcome translator."""

from __future__ import annotations

from auth.application.dtos import RequestOutcome


class DictOutcomeTranslator:
    def translate(self, outcome: RequestOutcome) -> dict[str, object]:
        return {
            "kind": outcome.kind.value,
            "account_id": str(outcome.identity.account_id) if outcome.identity and outcome.identity.account_id else None,
            "retry_after_seconds": outcome.retry_after_seconds,
            "return_target": outcome.return_target,
            "reason": outcome.reason,
        }
