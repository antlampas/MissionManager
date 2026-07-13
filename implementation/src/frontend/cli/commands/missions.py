# SPDX-License-Identifier: CC-BY-SA-4.0
import json
from dataclasses import asdict

import click

from ....application.services.mission_service import MissionService
from ..formatter import OutputFormatter
from ....domain.acl import Operation
from ....domain.enums import ResourceType
from .._utils import require_acl


@click.group("mission")
def mission_commands():
    """Gestione delle missioni (blueprint)."""
    pass


@mission_commands.command("list")
@require_acl(Operation.LIST, ResourceType.MISSION)
@click.option("--json", "as_json", is_flag=True, help="Output in formato JSON")
@click.pass_context
def list_missions(ctx, as_json: bool):
    """Elenca tutte le missioni."""
    svc: MissionService = ctx.obj["services"].mission
    missions = svc.list({})
    if as_json:
        click.echo(OutputFormatter.json_output([asdict(m) for m in missions]))
    else:
        click.echo(OutputFormatter.mission_table(missions))


@mission_commands.command("get")
@require_acl(Operation.VIEW, ResourceType.MISSION, "mission_id")
@click.argument("mission_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def get_mission(ctx, mission_id: str, as_json: bool):
    """Mostra il dettaglio di una missione."""
    svc: MissionService = ctx.obj["services"].mission
    dto = svc.get(mission_id)
    if as_json:
        click.echo(OutputFormatter.json_output(asdict(dto)))
    else:
        click.echo(f"ID    : {dto.id}")
        click.echo(f"Titolo: {dto.title}")
        click.echo(f"Descr : {dto.description}")
        click.echo(f"Policy: {dto.assignment_policy}")
        click.echo(f"Obiettivi ({len(dto.objectives)}):")
        for obj in dto.objectives:
            click.echo(f"  - {obj.description} ({len(obj.activities)} attività)")


@mission_commands.command("create")
@require_acl(Operation.CREATE_MISSION)
@click.option("--title", required=True, help="Titolo della missione")
@click.option("--desc", default="", help="Descrizione")
@click.option(
    "--objectives",
    required=True,
    help='JSON array di obiettivi: [{"description":"...","activities":[{"title":"..."}]}]',
)
@click.pass_context
def create_mission(ctx, title: str, desc: str, objectives: str):
    """Crea una nuova missione."""
    from ....domain.exceptions import MissionManagerError
    svc: MissionService = ctx.obj["services"].mission
    operator = ctx.obj.get("operator")
    try:
        obj_list = json.loads(objectives)
        dto = svc.create(
            title=title,
            desc=desc,
            objectives=obj_list,
            operator_id=operator.id if operator else None,
        )
        OutputFormatter.success(f"Missione creata: {dto.id}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@mission_commands.command("delete")
@require_acl(Operation.DELETE, ResourceType.MISSION, "mission_id")
@click.argument("mission_id")
@click.pass_context
def delete_mission(ctx, mission_id: str):
    """Elimina una missione."""
    from ....domain.exceptions import MissionManagerError
    svc: MissionService = ctx.obj["services"].mission
    operator = ctx.obj.get("operator")
    try:
        svc.delete(mission_id, operator_id=operator.id if operator else None)
        OutputFormatter.success(f"Missione {mission_id} eliminata")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)

# Nessun comando add-objective: il blueprint è immutabile dopo la creazione;
# obiettivi e attività si definiscono solo con `mission create` (vedi DESIGN §2.4).
