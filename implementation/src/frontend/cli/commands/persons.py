# SPDX-License-Identifier: CC-BY-SA-4.0
import click

from ....application.services.person_service import PersonService
from ..formatter import OutputFormatter
from ....domain.acl import Operation
from ....domain.enums import ResourceType
from .._utils import require_acl


@click.group("person")
def person_commands():
    """Gestione di persone e gruppi."""
    pass


@person_commands.command("list")
@require_acl(Operation.LIST, ResourceType.PERSON)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def list_persons(ctx, as_json):
    """Elenca tutte le persone."""
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    try:
        persons = svc.list({})
        if as_json:
            click.echo(OutputFormatter.json_output([p.__dict__ for p in persons]))
        else:
            for p in persons:
                groups = ",".join(p.acl_groups) or "—"
                click.echo(f"{p.id}  {p.primary_nickname}  (level={p.acl_level}, groups={groups})")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("get")
@require_acl(Operation.VIEW, ResourceType.PERSON, "person_id")
@click.argument("person_id")
@click.pass_context
def get_person(ctx, person_id):
    """Mostra il profilo di una persona."""
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    try:
        p = svc.get(person_id)
        click.echo(f"ID         : {p.id}")
        click.echo(f"Nickname   : {', '.join(p.nicknames)}")
        click.echo(f"ACL level  : {p.acl_level}")
        click.echo(f"ACL groups : {', '.join(p.acl_groups) or '—'}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("add")
@require_acl(Operation.CREATE_PERSON)
@click.option("--nickname", "nicknames", multiple=True, required=True)
@click.pass_context
def add_person(ctx, nicknames):
    """Aggiunge una nuova persona (profilo ACL meno privilegiato).

    Livello e gruppi ACL si assegnano con `person set-acl` (MANAGE_PROFILES).
    """
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    try:
        dto = svc.add(list(nicknames))
        OutputFormatter.success(f"Persona creata: {dto.id} ({dto.primary_nickname})")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("update")
@require_acl(Operation.EDIT, ResourceType.PERSON, "person_id")
@click.argument("person_id")
@click.option("--nickname", "nicknames", multiple=True, default=None)
@click.pass_context
def update_person(ctx, person_id, nicknames):
    """Aggiorna i nickname di una persona."""
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    try:
        dto = svc.update(
            person_id,
            nicknames=list(nicknames) if nicknames else None,
        )
        OutputFormatter.success(f"Persona {dto.id} aggiornata")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("set-acl")
@require_acl(Operation.MANAGE_PROFILES)
@click.argument("person_id")
@click.option(
    "--acl-level", type=int, default=None,
    help="Livello ACL (più basso = più privilegiato)",
)
@click.option(
    "--acl-group", "acl_groups", multiple=True,
    help="Gruppo ACL; ripetibile per assegnare più gruppi.",
)
@click.pass_context
def set_person_acl(ctx, person_id, acl_level, acl_groups):
    """Assegna il profilo ACL (livello e/o gruppi) di una persona."""
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    if acl_level is None and not acl_groups:
        OutputFormatter.error("Indicare almeno uno tra --acl-level e --acl-group")
        raise SystemExit(1)
    try:
        dto = svc.set_acl_profile(
            person_id,
            acl_level=acl_level,
            acl_groups=list(acl_groups) if acl_groups else None,
        )
        groups = ", ".join(dto.acl_groups) or "—"
        OutputFormatter.success(
            f"Profilo ACL aggiornato: livello {dto.acl_level}, gruppi: {groups}"
        )
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("remove")
@require_acl(Operation.DELETE, ResourceType.PERSON, "person_id")
@click.argument("person_id")
@click.pass_context
def remove_person(ctx, person_id):
    """Rimuove una persona."""
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    try:
        svc.remove(person_id)
        OutputFormatter.success(f"Persona {person_id} rimossa")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("group-list")
@require_acl(Operation.LIST, ResourceType.GROUP)
@click.pass_context
def list_groups(ctx):
    """Elenca tutti i gruppi."""
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    try:
        groups = svc.list_groups()
        for g in groups:
            click.echo(f"{g.id}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("group-add")
@require_acl(Operation.CREATE_GROUP)
@click.option("--name", default=None)
@click.option("--zone-type", type=click.Choice(["GEOGRAPHIC", "VIRTUAL"]), default=None)
@click.option("--zone-desc", default=None)
@click.pass_context
def add_group(ctx, name, zone_type, zone_desc):
    """Crea un nuovo gruppo."""
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    try:
        dto = svc.add_group(name=name, zone_type=zone_type, zone_description=zone_desc)
        OutputFormatter.success(f"Gruppo creato: {dto.id}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("group-update")
@require_acl(Operation.EDIT, ResourceType.GROUP, "group_id")
@click.argument("group_id")
@click.option("--name", default=None)
@click.option("--zone-type", type=click.Choice(["GEOGRAPHIC", "VIRTUAL"]), default=None)
@click.option("--zone-desc", default=None)
@click.pass_context
def update_group(ctx, group_id, name, zone_type, zone_desc):
    """Aggiorna nome e dati di zona di un gruppo."""
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    if name is None and zone_type is None and zone_desc is None:
        OutputFormatter.error("Indicare almeno uno tra --name, --zone-type e --zone-desc")
        raise SystemExit(1)
    try:
        dto = svc.update_group(
            group_id,
            name=name,
            zone_type=zone_type,
            zone_description=zone_desc,
        )
        label = dto.name or dto.id
        OutputFormatter.success(f"Gruppo aggiornato: {dto.id} ({label})")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("create-superuser")
@click.option("--nickname", default="admin", show_default=True, help="Username del superuser")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Password del superuser (min 12 caratteri, con maiuscola, cifra e simbolo)",
)
@click.pass_context
def create_superuser(ctx, nickname, password):
    """Crea l'amministratore iniziale (solo se non ne esiste già uno).

    Non richiede autenticazione: serve per il bootstrap iniziale.
    - Backend locale: disponibile solo su database vuoto.
    - Backend OIDC:   crea l'utente nell'identity provider con ACL livello
      amministratore, delegando creazione e password all'IdP. Disponibile
      finché l'IdP non contiene già un amministratore.
    """
    from ....domain.exceptions import MissionManagerError

    svc: PersonService = ctx.obj["services"].person
    auth_service = ctx.obj.get("auth_service")

    if auth_service is None:
        OutputFormatter.error(
            "auth_service non disponibile: impossibile creare l'amministratore iniziale."
        )
        raise SystemExit(1)

    try:
        if auth_service.admin_exists(svc):
            OutputFormatter.error(
                "Esiste già un amministratore. "
                "Il comando create-superuser è disponibile solo prima del primo avvio."
            )
            raise SystemExit(1)

        from ....application.services.auth_service import INITIAL_ADMIN_ACL_LEVEL

        person = auth_service.create_initial_admin(svc, nickname, password)
        OutputFormatter.success(
            f"Amministratore '{nickname}' creato "
            f"(ID: {person.id}, ACL level: {INITIAL_ADMIN_ACL_LEVEL})."
        )
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("group-remove")
@require_acl(Operation.DELETE, ResourceType.GROUP, "group_id")
@click.argument("group_id")
@click.pass_context
def remove_group(ctx, group_id):
    """Rimuove un gruppo."""
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    try:
        svc.remove_group(group_id)
        OutputFormatter.success(f"Gruppo {group_id} rimosso")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("group-members")
@require_acl(Operation.VIEW, ResourceType.GROUP, "group_id")
@click.argument("group_id")
@click.pass_context
def group_members(ctx, group_id):
    """Elenca i membri di un gruppo."""
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    try:
        members = svc.list_by_group(group_id)
        for p in members:
            click.echo(f"{p.id}  {p.primary_nickname}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("group-member-add")
@require_acl(Operation.MANAGE_MEMBERS, ResourceType.GROUP, "group_id")
@click.argument("group_id")
@click.argument("person_id")
@click.pass_context
def add_group_member(ctx, group_id, person_id):
    """Aggiunge una persona a un gruppo."""
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    try:
        svc.add_group_member(group_id, person_id)
        OutputFormatter.success(f"Persona {person_id} aggiunta al gruppo {group_id}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@person_commands.command("group-member-remove")
@require_acl(Operation.MANAGE_MEMBERS, ResourceType.GROUP, "group_id")
@click.argument("group_id")
@click.argument("person_id")
@click.pass_context
def remove_group_member(ctx, group_id, person_id):
    """Rimuove una persona da un gruppo."""
    from ....domain.exceptions import MissionManagerError
    svc: PersonService = ctx.obj["services"].person
    try:
        svc.remove_group_member(group_id, person_id)
        OutputFormatter.success(f"Persona {person_id} rimossa dal gruppo {group_id}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)
