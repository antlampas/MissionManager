# SPDX-License-Identifier: CC-BY-SA-4.0
import click

from ....application.services.badge_service import BadgeService
from ..formatter import OutputFormatter
from ....domain.acl import Operation
from ....domain.enums import ResourceType
from .._utils import require_acl


@click.group("badge")
def badge_commands():
    """Gestione dei badge."""
    pass


@badge_commands.command("list")
@require_acl(Operation.LIST, ResourceType.BADGE)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def list_badges(ctx, as_json):
    """Elenca tutti i badge disponibili."""
    from ....domain.exceptions import MissionManagerError
    svc: BadgeService = ctx.obj["services"].badge
    try:
        badges = svc.list()
        if as_json:
            click.echo(OutputFormatter.json_output([b.__dict__ for b in badges]))
        else:
            for b in badges:
                click.echo(f"{b.id}  {b.name}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@badge_commands.command("create")
@require_acl(Operation.CREATE_BADGE)
@click.option("--name", required=True)
@click.option("--desc", default="")
@click.option("--image-url", default=None)
@click.pass_context
def create_badge(ctx, name, desc, image_url):
    """Crea un nuovo badge."""
    from ....domain.exceptions import MissionManagerError
    svc: BadgeService = ctx.obj["services"].badge
    operator = ctx.obj.get("operator")
    try:
        dto = svc.create(
            name=name,
            desc=desc,
            image_url=image_url,
            operator_id=operator.id if operator else None,
        )
        OutputFormatter.success(f"Badge creato: {dto.id} — {dto.name}")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@badge_commands.command("award-assignment")
@require_acl(Operation.AWARD_BADGE, ResourceType.ASSIGNMENT, "assignment_id")
@click.option("--badge-id", required=True)
@click.option("--assignment-id", required=True)
@click.pass_context
def award_assignment(ctx, badge_id, assignment_id):
    """Assegna un badge a un assignment completato."""
    from ....domain.exceptions import MissionManagerError
    svc: BadgeService = ctx.obj["services"].badge
    operator = ctx.obj.get("operator")
    try:
        dto = svc.award_to_assignment(
            badge_id=badge_id,
            assignment_id=assignment_id,
            operator_id=operator.id if operator else None,
        )
        click.echo(OutputFormatter.badge_award(dto))
        OutputFormatter.success("Badge conferito")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)


@badge_commands.command("award-activity")
@require_acl(Operation.AWARD_BADGE, ResourceType.ACTIVITY, "activity_id")
@click.option("--badge-id", required=True)
@click.option("--activity-id", required=True)
@click.pass_context
def award_activity(ctx, badge_id, activity_id):
    """Assegna un badge a un'attività completata."""
    from ....domain.exceptions import MissionManagerError
    svc: BadgeService = ctx.obj["services"].badge
    operator = ctx.obj.get("operator")
    try:
        dto = svc.award_to_activity(
            badge_id=badge_id,
            activity_id=activity_id,
            operator_id=operator.id if operator else None,
        )
        click.echo(OutputFormatter.badge_award(dto))
        OutputFormatter.success("Badge conferito")
    except MissionManagerError as exc:
        OutputFormatter.error(exc.message)
        raise SystemExit(1)
