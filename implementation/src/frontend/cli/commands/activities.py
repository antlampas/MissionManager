# SPDX-License-Identifier: CC-BY-SA-4.0
import click

from ....application.services.activity_service import ActivityService
from ..formatter import OutputFormatter
from ....domain.acl import Operation
from ....domain.enums import ResourceType
from .._utils import require_acl


@click.group("activity")
def activity_commands():
    """Gestione delle attività."""
    pass


@activity_commands.command("get")
@require_acl(Operation.VIEW, ResourceType.ACTIVITY, "activity_id")
@click.argument("activity_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def get_activity(ctx, activity_id, as_json):
    """Mostra il dettaglio di un'attività."""
    from ....domain.exceptions import MissionManagerError
    svc: ActivityService = ctx.obj["services"].activity
    try:
        dto = svc.get(activity_id)
        if as_json:
            click.echo(OutputFormatter.json_output(dto.__dict__))
        else:
            click.echo(f"ID    : {dto.id}")
            click.echo(f"Titolo: {dto.title}")
            click.echo(f"Stato : {dto.status}")
            click.echo(f"Assegnatari: {', '.join(dto.assignees) or '—'}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@activity_commands.command("assign")
@require_acl(Operation.ASSIGN, ResourceType.ACTIVITY, "activity_id")
@click.argument("activity_id")
@click.option("--person-id", required=True)
@click.pass_context
def assign_activity(ctx, activity_id, person_id):
    """Assegna un'attività a una persona."""
    from ....domain.exceptions import MissionManagerError
    svc: ActivityService = ctx.obj["services"].activity
    operator = ctx.obj.get("operator")
    try:
        dto = svc.assign_to(
            activity_id, person_id, operator_id=operator.id if operator else None
        )
        OutputFormatter.success(f"Attività {dto.id} assegnata a {person_id}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@activity_commands.command("unassign")
@require_acl(Operation.ASSIGN, ResourceType.ACTIVITY, "activity_id")
@click.argument("activity_id")
@click.option("--person-id", required=True)
@click.pass_context
def unassign_activity(ctx, activity_id, person_id):
    """Rimuove un assegnatario da un'attività."""
    from ....domain.exceptions import MissionManagerError
    svc: ActivityService = ctx.obj["services"].activity
    operator = ctx.obj.get("operator")
    try:
        dto = svc.unassign(
            activity_id, person_id, operator_id=operator.id if operator else None
        )
        OutputFormatter.success(f"Assegnatario {person_id} rimosso dall'attività {dto.id}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@activity_commands.command("status")
@require_acl(Operation.UPDATE_STATUS, ResourceType.ACTIVITY, "activity_id")
@click.argument("activity_id")
@click.argument("new_status", type=click.Choice(["ASSIGNED", "IN_PROGRESS", "COMPLETED", "FAILED"]))
@click.pass_context
def update_status(ctx, activity_id, new_status):
    """Aggiorna lo stato di un'attività."""
    from ....domain.exceptions import MissionManagerError
    svc: ActivityService = ctx.obj["services"].activity
    operator = ctx.obj.get("operator")
    try:
        dto = svc.update_status(
            activity_id,
            new_status,
            operator_id=operator.id if operator else None,
        )
        OutputFormatter.success(f"Attività {dto.id}: stato aggiornato a {dto.status}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)
