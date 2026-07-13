# SPDX-License-Identifier: CC-BY-SA-4.0
import json
from typing import Any

import click

from ...application.services.dto import AssignmentDTO, BadgeAwardDTO, MissionDTO


class OutputFormatter:
    """Centralizza la presentazione dei dati su stdout per la CLI."""

    @staticmethod
    def mission_table(missions: list[MissionDTO]) -> str:
        if not missions:
            return "(nessuna missione trovata)"
        header = f"{'ID':<38} {'Titolo':<30} {'Obiettivi':>9} {'Policy'}"
        sep = "-" * 90
        rows = []
        for m in missions:
            policy = "unlimited"
            if not m.assignment_policy.get("unlimited"):
                parts = []
                if "max_total" in m.assignment_policy:
                    parts.append(f"max_total={m.assignment_policy['max_total']}")
                if "max_concurrent" in m.assignment_policy:
                    parts.append(f"max_concurrent={m.assignment_policy['max_concurrent']}")
                policy = ", ".join(parts)
            rows.append(
                f"{m.id:<38} {m.title[:29]:<30} {len(m.objectives):>9}  {policy}"
            )
        return "\n".join([header, sep] + rows)

    @staticmethod
    def assignment_detail(dto: AssignmentDTO) -> str:
        lines = [
            f"Assignment : {dto.id}",
            f"Missione   : {dto.mission_id}",
            f"Stato      : {dto.status}",
            f"Assegnatario: {dto.assignee_type} / {dto.assignee_id}",
            f"Esito      : {dto.outcome or 'n/d'}",
            "",
            "Obiettivi:",
        ]
        for obj in dto.objectives:
            lines.append(f"  [{obj.outcome or '...'}] {obj.description}")
            for act in obj.activities:
                assignees = ", ".join(act.assignees) or "—"
                lines.append(
                    f"      [{act.status}] {act.title} (assegnatari: {assignees})"
                )
        return "\n".join(lines)

    @staticmethod
    def badge_award(dto: BadgeAwardDTO) -> str:
        return (
            f"Badge      : {dto.badge.name}\n"
            f"Target     : {dto.target_type} {dto.target_id}\n"
            f"Data       : {dto.awarded_at}\n"
            f"Destinatari: {dto.recipients_count} "
            f"({', '.join(dto.recipients[:3])}{'...' if dto.recipients_count > 3 else ''})"
        )

    @staticmethod
    def json_output(data: Any) -> str:
        return json.dumps(data, indent=2, default=str)

    @staticmethod
    def success(msg: str) -> None:
        click.echo(f"✓ {msg}")

    @staticmethod
    def error(msg: str) -> None:
        click.echo(f"✗ {msg}", err=True)
