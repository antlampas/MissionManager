# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

import inspect
from typing import Optional

from ..domain.exceptions import ExtensionConflictError, NotFoundError
from ..domain.extensions import (
    ExtensionManifest,
    ExtensionRequest,
    ExtensionResult,
    MissionExtension,
)


class ExtensionRegistry:
    """Registro delle estensioni applicative. Indicizza per id stabile."""

    def __init__(self) -> None:
        self._extensions: dict[str, MissionExtension] = {}
        self._registered_routes: set[tuple[str, str]] = set()
        self._registered_commands: set[str] = set()

    def register(self, extension: MissionExtension) -> None:
        ext_id = extension.manifest.id
        if ext_id in self._extensions:
            raise ExtensionConflictError(f"Estensione '{ext_id}' già registrata")
        route_keys: set[tuple[str, str]] = set()
        for route in extension.manifest.provides_routes:
            method = route.method.upper()
            expected_prefix = f"/extensions/{ext_id}/"
            if not route.path.startswith(expected_prefix) and route.path != f"/extensions/{ext_id}":
                raise ExtensionConflictError(
                    f"Il path {route.path!r} non rispetta il namespace /extensions/{ext_id}/"
                )
            route_key = (method, route.path)
            if route_key in self._registered_routes or route_key in route_keys:
                raise ExtensionConflictError(
                    f"Collisione di route: {method} {route.path!r} già registrata"
                )
            route_keys.add(route_key)
        command_names: set[str] = set()
        for command in extension.manifest.provides_commands:
            if command.name in self._registered_commands or command.name in command_names:
                raise ExtensionConflictError(
                    f"Collisione di comando CLI: {command.name!r} già registrato"
                )
            command_names.add(command.name)
        # Registrazione atomica: nessuna riga sopra ha effetti collaterali.
        self._registered_routes.update(route_keys)
        self._registered_commands.update(command_names)
        self._extensions[ext_id] = extension

    def get(self, ext_name: str) -> Optional[MissionExtension]:
        return self._extensions.get(ext_name)

    def list(self) -> list[ExtensionManifest]:
        return [ext.manifest for ext in self._extensions.values()]

    def execute(self, ext_name: str, request: ExtensionRequest) -> ExtensionResult:
        extension = self._extensions.get(ext_name)
        if extension is None:
            raise NotFoundError(
                f"Estensione '{ext_name}' non trovata",
                resource_type="extension",
            )
        return _execute_extension(extension, request)

    def unregister(self, ext_name: str) -> None:
        ext = self._extensions.pop(ext_name, None)
        if ext:
            for route in ext.manifest.provides_routes:
                self._registered_routes.discard((route.method.upper(), route.path))
            for command in ext.manifest.provides_commands:
                self._registered_commands.discard(command.name)


def accepts_subject(execute_method) -> bool:
    """True se ``execute`` accetta un secondo argomento posizionale (subject).

    Conta solo i parametri che possono ricevere un posizionale: ``**kwargs``
    non basta (non accetta posizionali), mentre ``*args`` sì.
    """
    try:
        params = list(inspect.signature(execute_method).parameters.values())
    except (TypeError, ValueError):
        return False
    if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params):
        return True
    positional = [
        p
        for p in params
        if p.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional) >= 2


def _execute_extension(ext: MissionExtension, request: ExtensionRequest) -> ExtensionResult:
    execute = ext.execute
    if accepts_subject(execute):
        return execute(request, request.subject)  # type: ignore[misc]
    return execute(request)
