# SPDX-License-Identifier: CC-BY-SA-4.0
"""Comandi CLI di gestione delle AclEntry (DESIGN §10).

L'autorizzazione è applicata da AclService stesso (autoprotezione MANAGE_ACL
sulla risorsa o su SYSTEM:global): i comandi non hanno un decorator ACL
proprio — un operatore non autorizzato riceve l'errore del service.
"""
import click

from ....application.services.acl_service import AclService
from ....domain.acl import Operation, Permission
from ..formatter import OutputFormatter


@click.group("acl")
def acl_commands():
    """Gestione delle regole ACL (entry)."""
    pass


def _operator_id(ctx):
    operator = ctx.obj.get("operator")
    return operator.id if operator is not None else None


@acl_commands.command("list")
@click.option("--resource-type", default=None, help="Filtra per tipo di risorsa")
@click.option("--resource-id", default=None, help="Filtra per id risorsa (UUID, «*» o «global»)")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def list_entries(ctx, resource_type, resource_id, as_json):
    """Elenca le entry ACL (tutte, o quelle di una risorsa)."""
    from ....domain.exceptions import MissionManagerError
    svc: AclService = ctx.obj["services"].acl
    try:
        if resource_type and resource_id:
            entries = svc.list_entries(
                resource_type, resource_id, operator_id=_operator_id(ctx)
            )
        else:
            entries = svc.list_all_entries(operator_id=_operator_id(ctx))
        if as_json:
            click.echo(OutputFormatter.json_output([e.__dict__ for e in entries]))
            return
        for e in entries:
            subject = "PUBLIC" if e.subject_type == "PUBLIC" else f"USER({e.subject_id})"
            level = f"level<={e.level}" if e.level is not None else "-"
            group = f"group={e.group}" if e.group else "-"
            click.echo(
                f"{e.id}  {e.permission:5} {e.operation:17} "
                f"{e.resource_type}:{e.resource_id}  {subject}  {level} {e.profile_join} {group}"
            )
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@acl_commands.command("add")
@click.option("--resource-type", required=True)
@click.option("--resource-id", required=True, help="UUID, «*» (radice di tipo) o «global» (SYSTEM)")
@click.option(
    "--operation", "operation_", required=True,
    type=click.Choice([op.value for op in Operation]),
)
@click.option(
    "--permission", required=True,
    type=click.Choice([perm.value for perm in Permission]),
)
@click.option("--subject-id", default=None, help="UUID della persona; assente = PUBLIC")
@click.option("--level", type=int, default=None, help="Soglia di livello (soddisfatta da livello <= L)")
@click.option("--group", default=None, help="Gruppo ACL richiesto")
@click.option("--profile-join", type=click.Choice(["OR", "AND"]), default="OR", show_default=True)
@click.option("--subject-join", type=click.Choice(["AND", "OR"]), default="AND", show_default=True)
@click.pass_context
def add_entry(
    ctx, resource_type, resource_id, operation_, permission,
    subject_id, level, group, profile_join, subject_join,
):
    """Crea una entry ACL (almeno uno tra --level e --group, INV-1)."""
    from ....domain.exceptions import MissionManagerError
    svc: AclService = ctx.obj["services"].acl
    try:
        dto = svc.create_entry(
            resource_type=resource_type,
            resource_id=resource_id,
            operation=operation_,
            permission=permission,
            subject_id=subject_id,
            level=level,
            group=group,
            profile_join=profile_join,
            subject_join=subject_join,
            operator_id=_operator_id(ctx),
        )
        OutputFormatter.success(
            f"Entry creata: {dto.id} — {dto.permission} {dto.operation} "
            f"su {dto.resource_type}:{dto.resource_id}"
        )
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@acl_commands.command("remove")
@click.argument("entry_id")
@click.pass_context
def remove_entry(ctx, entry_id):
    """Elimina una entry ACL."""
    from ....domain.exceptions import MissionManagerError
    svc: AclService = ctx.obj["services"].acl
    try:
        svc.delete_entry(entry_id, operator_id=_operator_id(ctx))
        OutputFormatter.success(f"Entry {entry_id} eliminata")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)
