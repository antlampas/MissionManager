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

    def register(self, extension: MissionExtension) -> None:
        ext_id = extension.manifest.id
        if ext_id in self._extensions:
            raise ExtensionConflictError(f"Estensione '{ext_id}' già registrata")
        for route in extension.manifest.provides_routes:
            method = route.method.upper()
            expected_prefix = f"/extensions/{ext_id}/"
            if not route.path.startswith(expected_prefix) and route.path != f"/extensions/{ext_id}":
                raise ExtensionConflictError(
                    f"Il path {route.path!r} non rispetta il namespace /extensions/{ext_id}/"
                )
            route_key = (method, route.path)
            if route_key in self._registered_routes:
                raise ExtensionConflictError(
                    f"Collisione di route: {method} {route.path!r} già registrata"
                )
            self._registered_routes.add(route_key)
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


def _execute_extension(ext: MissionExtension, request: ExtensionRequest) -> ExtensionResult:
    execute = ext.execute
    try:
        params = inspect.signature(execute).parameters
    except (TypeError, ValueError):
        params = {}
    if len(params) >= 2:
        return execute(request, request.subject)  # type: ignore[misc]
    return execute(request)
