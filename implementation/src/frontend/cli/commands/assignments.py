# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import asdict

import click

from ....application.services.assignment_service import AssignmentService
from ..formatter import OutputFormatter
from ....domain.acl import Operation
from ....domain.enums import ResourceType
from .._utils import require_acl


@click.group("assignment")
def assignment_commands():
    """Gestione degli assignment."""
    pass


@assignment_commands.command("create")
@require_acl(Operation.CREATE_ASSIGNMENT, ResourceType.MISSION, "mission_id")
@click.option("--mission-id", required=True)
@click.option("--assignee-type", type=click.Choice(["PERSON", "GROUP"]), default=None)
@click.option("--assignee-id", default=None)
@click.pass_context
def create_assignment(ctx, mission_id, assignee_type, assignee_id):
    """Crea un nuovo assignment per una missione."""
    from ....domain.exceptions import MissionManagerError
    svc: AssignmentService = ctx.obj["services"].assignment
    operator = ctx.obj.get("operator")
    try:
        dto = svc.create(
            mission_id=mission_id,
            assignee_type=assignee_type,
            assignee_id=assignee_id,
            operator_id=operator.id if operator else None,
        )
        OutputFormatter.success(f"Assignment creato: {dto.id} (stato: {dto.status})")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@assignment_commands.command("assign")
@require_acl(Operation.ASSIGN, ResourceType.ASSIGNMENT, "assignment_id")
@click.argument("assignment_id")
@click.option("--type", "assignee_type", required=True, type=click.Choice(["PERSON", "GROUP"]))
@click.option("--id", "assignee_id", required=True)
@click.pass_context
def assign_assignment(ctx, assignment_id, assignee_type, assignee_id):
    """Assegna un assignment a una persona o un gruppo."""
    from ....domain.exceptions import MissionManagerError
    svc: AssignmentService = ctx.obj["services"].assignment
    operator = ctx.obj.get("operator")
    try:
        dto = svc.assign(
            assignment_id, assignee_type, assignee_id,
            operator_id=operator.id if operator else None,
        )
        OutputFormatter.success(f"Assignment {dto.id} assegnato (stato: {dto.status})")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@assignment_commands.command("get")
@require_acl(Operation.VIEW, ResourceType.ASSIGNMENT, "assignment_id")
@click.argument("assignment_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def get_assignment(ctx, assignment_id, as_json):
    """Mostra il dettaglio di un assignment."""
    from ....domain.exceptions import MissionManagerError
    svc: AssignmentService = ctx.obj["services"].assignment
    try:
        dto = svc.get(assignment_id)
        if as_json:
            click.echo(OutputFormatter.json_output(asdict(dto)))
        else:
            click.echo(OutputFormatter.assignment_detail(dto))
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@assignment_commands.command("status")
@require_acl(Operation.UPDATE_STATUS, ResourceType.ASSIGNMENT, "assignment_id")
@click.argument("assignment_id")
@click.argument("new_status", type=click.Choice(["ASSIGNED", "IN_PROGRESS", "COMPLETED", "FAILED"]))
@click.pass_context
def update_status(ctx, assignment_id, new_status):
    """Aggiorna lo stato di un assignment."""
    from ....domain.exceptions import MissionManagerError
    svc: AssignmentService = ctx.obj["services"].assignment
    operator = ctx.obj.get("operator")
    try:
        dto = svc.update_status(
            assignment_id, new_status, operator_id=operator.id if operator else None
        )
        OutputFormatter.success(f"Assignment {dto.id}: stato aggiornato a {dto.status}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)
