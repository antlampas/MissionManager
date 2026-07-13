# SPDX-License-Identifier: CC-BY-SA-4.0
"""Bootstrap CLI frontend."""
from __future__ import annotations

import os
from typing import Optional
from uuid import UUID

from ..infrastructure.identity.cli import CliOperatorIdentityAdapter
from ..config import CliConfigLoader
from ..frontend.cli.app import CLIApp
from .common import build_system_for_cli


def create_cli_app(config_file: Optional[str] = None) -> CLIApp:
    """Costruisce il gruppo CLI con tutti i componenti wired.

    ``config_file`` è il path del file di configurazione; se ``None`` viene letto
    da ``MISSIONMANAGER_CONFIG_FILE``.
    """
    resolved_config = config_file or os.environ.get("MISSIONMANAGER_CONFIG_FILE")
    cli_config = CliConfigLoader.load(resolved_config)
    svcs = build_system_for_cli(resolved_config)

    operator_id: Optional[UUID] = None
    if cli_config.operator_id:
        try:
            operator_id = UUID(cli_config.operator_id)
        except ValueError as exc:
            raise RuntimeError(
                f"MISSIONMANAGER_OPERATOR_ID non è un UUID valido: {cli_config.operator_id}"
            ) from exc

    identity_adapter = CliOperatorIdentityAdapter(
        person_repo=svcs.person_repo,
        operator_id=operator_id,
        identity_mode=cli_config.identity_mode,
        uow=svcs.uow,
    )

    return CLIApp(
        mission_svc=svcs.mission,
        assignment_svc=svcs.assignment,
        activity_svc=svcs.activity,
        badge_svc=svcs.badge,
        person_svc=svcs.person,
        acl_svc=svcs.acl,
        extension_registry=svcs.extension_registry,
        auth_policy=svcs.auth_policy,
        operator_provider=identity_adapter,
        auth_service=svcs.auth_service,
        event_publisher=svcs.event_publisher,
    )


def run_cli(config_file: Optional[str] = None) -> None:
    app = create_cli_app(config_file)
    app.run()
