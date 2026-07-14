# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import click

from ...domain.exceptions import ACLError, MissionManagerError
from ...domain.extensions import ExtensionRequest
from ...application.services.acl_service import AclService
from ...application.services.activity_service import ActivityService
from ...application.services.assignment_service import AssignmentService
from ...application.authorization import AuthorizationPolicy
from ...application.services.badge_service import BadgeService
from ...application.extension_registry import ExtensionRegistry
from ...application.services.mission_service import MissionService
from ...application.services.person_service import PersonService
from .commands.acl import acl_commands
from .commands.activities import activity_commands
from .commands.assignments import assignment_commands
from .commands.badges import badge_commands
from .commands.missions import mission_commands
from .commands.persons import person_commands
from .formatter import OutputFormatter
# require_acl vive in _utils (modulo foglia) per evitare l'import circolare
# app → commands.* → app; qui serve solo ai comandi delle estensioni.
from ...domain.acl import Operation
from ._utils import require_acl


@dataclass
class Services:
    """Container dei service applicativi passato nel Click context."""

    mission: MissionService
    assignment: AssignmentService
    activity: ActivityService
    badge: BadgeService
    person: PersonService
    acl: AclService
    extensions: ExtensionRegistry


def create_cli(
    mission_svc: MissionService,
    assignment_svc: AssignmentService,
    activity_svc: ActivityService,
    badge_svc: BadgeService,
    person_svc: PersonService,
    acl_svc: AclService,
    extension_registry: ExtensionRegistry,
    auth_policy: AuthorizationPolicy,
    operator_provider=None,
    auth_service=None,
    event_publisher=None,
) -> click.Group:
    """Costruisce il gruppo CLI radice con tutti i sottogruppi e le estensioni."""

    services = Services(
        mission=mission_svc,
        assignment=assignment_svc,
        activity=activity_svc,
        badge=badge_svc,
        person=person_svc,
        acl=acl_svc,
        extensions=extension_registry,
    )

    @click.group()
    @click.pass_context
    def cli(ctx):
        """MissionManager — CLI operativa."""
        ctx.ensure_object(dict)
        ctx.obj["services"] = services
        ctx.obj["auth_policy"] = auth_policy
        ctx.obj["auth_service"] = auth_service
        if operator_provider is not None:
            try:
                ctx.obj["operator"] = operator_provider.get_current_operator()
            except MissionManagerError as exc:
                OutputFormatter.error(exc.message)
                raise SystemExit(1)
        else:
            ctx.obj["operator"] = None

    cli.add_command(mission_commands)
    cli.add_command(assignment_commands)
    cli.add_command(activity_commands)
    cli.add_command(badge_commands)
    cli.add_command(person_commands)
    cli.add_command(acl_commands)

    # Registrazione dinamica comandi da estensioni. I nomi già in uso
    # (comandi core o di altre estensioni) non vengono mai sovrascritti:
    # l'omonimo dell'estensione è scartato con un errore nel log.
    for manifest in extension_registry.list():
        for cmd_spec in manifest.provides_commands:
            if cmd_spec.name in cli.commands:
                logging.getLogger(__name__).error(
                    "CLI: comando %r dell'estensione %s ignorato: nome già in uso",
                    cmd_spec.name,
                    manifest.id,
                )
                continue
            _add_extension_command(cli, manifest.id, cmd_spec, extension_registry)

    return cli


def _add_extension_command(
    cli: click.Group,
    ext_name: str,
    cmd_spec,
    extension_registry: ExtensionRegistry,
) -> None:
    @cli.command(name=cmd_spec.name)
    @require_acl(Operation.EXECUTE)
    @click.option(
        "--param",
        "params",
        multiple=True,
        help="Parametro estensione in forma chiave=valore; ripetibile.",
    )
    @click.pass_context
    def ext_command(ctx, params, _ext_name=ext_name):
        operator = ctx.obj.get("operator")
        op_id = operator.id if operator else None
        parsed_params = {}
        for item in params:
            if "=" not in item:
                raise click.BadParameter("Usa il formato chiave=valore", param_hint="--param")
            key, value = item.split("=", 1)
            if not key:
                raise click.BadParameter("La chiave non può essere vuota", param_hint="--param")
            parsed_params[key] = value
        try:
            result = extension_registry.execute(
                _ext_name,
                ExtensionRequest(operator_id=op_id, params=parsed_params, body=parsed_params),
            )
        except MissionManagerError as exc:
            # Include il veto di un plugin BEFORE_* (OperationAbortedError).
            OutputFormatter.error(exc.message)
            raise SystemExit(1)
        click.echo(OutputFormatter.json_output(result.data))


class CLIApp:
    """Punto di ingresso della CLI. Aggrega il bootstrap e il Click group."""

    def __init__(
        self,
        mission_svc: MissionService,
        assignment_svc: AssignmentService,
        activity_svc: ActivityService,
        badge_svc: BadgeService,
        person_svc: PersonService,
        acl_svc: AclService,
        extension_registry: ExtensionRegistry,
        auth_policy: AuthorizationPolicy,
        operator_provider=None,
        auth_service=None,
        event_publisher=None,
    ) -> None:
        self.cli = create_cli(
            mission_svc=mission_svc,
            assignment_svc=assignment_svc,
            activity_svc=activity_svc,
            badge_svc=badge_svc,
            person_svc=person_svc,
            acl_svc=acl_svc,
            extension_registry=extension_registry,
            auth_policy=auth_policy,
            operator_provider=operator_provider,
            auth_service=auth_service,
        )
        self._event_publisher = event_publisher

    def run(self, args: Optional[list[str]] = None, standalone_mode: bool = True) -> Any:
        try:
            return self.cli(args=args, standalone_mode=standalone_mode)
        finally:
            if self._event_publisher is not None:
                self._event_publisher.dispatch_consumer("audit")
