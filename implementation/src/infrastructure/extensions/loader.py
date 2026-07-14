# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from ...application.extension_registry import accepts_subject
from ...domain.extensions import (
    CommandSpec,
    ExtensionManifest,
    MissionExtension,
    RouteSpec,
)
from .installed_registry import InstalledManifestRegistry

logger = logging.getLogger(__name__)

_CHECKSUM_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")


class ExtensionLoader:
    """Load approved extension bundles."""

    def __init__(
        self,
        scan_paths: list[str],
        installed_registry: InstalledManifestRegistry | None = None,
        **services: Any,
    ) -> None:
        self._scan_paths = scan_paths
        self._registry = installed_registry or InstalledManifestRegistry()
        self._services = services

    def load_all(self) -> list[MissionExtension]:
        if not self._scan_paths:
            logger.debug("ExtensionLoader: nessun percorso estensioni configurato")
            return []
        if self._registry.is_empty():
            logger.warning(
                "ExtensionLoader: InstalledManifestRegistry vuoto o assente; nessuna estensione caricata"
            )
            return []

        extensions: list[MissionExtension] = []
        seen_ids: set[str] = set()
        for bundle_dir in self._bundle_dirs():
            extension = self._load_bundle(bundle_dir)
            if extension is None:
                continue
            if extension.manifest.id in seen_ids:
                logger.warning(
                    "ExtensionLoader: estensione duplicata %s in %s; ignorata",
                    extension.manifest.id,
                    bundle_dir,
                )
                continue
            seen_ids.add(extension.manifest.id)
            extensions.append(extension)
        return extensions

    def _bundle_dirs(self) -> list[Path]:
        bundles: list[Path] = []
        seen: set[Path] = set()

        def _add(candidate: Path) -> None:
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                bundles.append(candidate)

        for raw_path in self._scan_paths:
            scan_dir = Path(raw_path)
            if not scan_dir.is_dir():
                logger.warning("ExtensionLoader: directory non trovata %s", raw_path)
                continue
            if (scan_dir / "manifest.json").is_file() and (scan_dir / "extension.py").is_file():
                _add(scan_dir)
                continue
            for child in sorted(scan_dir.iterdir()):
                if (
                    child.is_dir()
                    and (child / "manifest.json").is_file()
                    and (child / "extension.py").is_file()
                ):
                    _add(child)
        return bundles

    def _load_bundle(self, bundle_dir: Path) -> MissionExtension | None:
        manifest_path = bundle_dir / "manifest.json"
        code_path = bundle_dir / "extension.py"
        try:
            manifest_raw = manifest_path.read_bytes()
            manifest_data = json.loads(manifest_raw.decode("utf-8"))
        except Exception as exc:
            logger.error("ExtensionLoader: manifest non valido in %s: %s", bundle_dir, exc)
            return None
        if not isinstance(manifest_data, dict):
            logger.error("ExtensionLoader: manifest non oggetto in %s", bundle_dir)
            return None

        ext_id = str(manifest_data.get("id") or "")
        if not ext_id:
            logger.error("ExtensionLoader: manifest senza id in %s", bundle_dir)
            return None
        entry = self._registry.get_entry(ext_id)
        if entry is None:
            logger.error("ExtensionLoader: estensione %s non approvata", ext_id)
            return None

        actual_manifest_checksum = _sha256_bytes(manifest_raw)
        if actual_manifest_checksum != entry.manifest_checksum:
            logger.error("ExtensionLoader: manifest checksum non valido per %s", ext_id)
            return None

        actual_code_checksum = _sha256_file(code_path)
        try:
            declared_code_checksum = _normalize_checksum(
                manifest_data.get("code_checksum") or entry.code_checksum
            )
        except ValueError as exc:
            logger.error("ExtensionLoader: code_checksum non valido per %s: %s", ext_id, exc)
            return None
        if actual_code_checksum != entry.code_checksum or declared_code_checksum != entry.code_checksum:
            logger.error("ExtensionLoader: code checksum non valido per %s", ext_id)
            return None

        try:
            manifest = _manifest_from_data(manifest_data, entry.code_checksum)
        except ValueError as exc:
            logger.error("ExtensionLoader: manifest non valido per %s: %s", ext_id, exc)
            return None

        module = self._import_module(code_path, ext_id, actual_code_checksum)
        if module is None:
            return None
        extension_class = getattr(module, "Extension", None)
        if extension_class is None:
            logger.error("ExtensionLoader: classe Extension non trovata in %s", code_path)
            return None
        try:
            inner = _instantiate_extension(extension_class, manifest, self._services)
        except Exception as exc:
            logger.error("ExtensionLoader: impossibile istanziare %s: %s", ext_id, exc)
            return None
        return _LoadedExtension(inner, manifest)

    @staticmethod
    def _import_module(code_path: Path, ext_id: str, checksum: str) -> Any | None:
        module_name = f"extension_{_safe_name(ext_id)}_{checksum[-12:]}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, code_path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)  # type: ignore[union-attr]
            except Exception:
                sys.modules.pop(module_name, None)
                raise
            return module
        except Exception as exc:
            logger.error("ExtensionLoader: impossibile importare %s: %s", code_path, exc)
            return None


class _LoadedExtension:
    def __init__(self, inner: Any, manifest: ExtensionManifest) -> None:
        self._inner = inner
        self._manifest = manifest
        self._accepts_subject = accepts_subject(inner.execute)

    @property
    def manifest(self) -> ExtensionManifest:
        return self._manifest

    def execute(self, request):
        if self._accepts_subject:
            return self._inner.execute(request, request.subject)
        return self._inner.execute(request)


def _instantiate_extension(
    extension_class: type,
    manifest: ExtensionManifest,
    services: dict[str, Any],
) -> Any:
    try:
        signature = inspect.signature(extension_class)
    except (TypeError, ValueError):
        signature = None
    if signature is None:
        return extension_class(manifest=manifest, **services)

    params = signature.parameters
    accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    kwargs: dict[str, Any] = {}
    if "manifest" in params or accepts_kwargs:
        kwargs["manifest"] = manifest
    for name, service in services.items():
        if name in params or accepts_kwargs:
            kwargs[name] = service
    return extension_class(**kwargs)


def _manifest_from_data(data: dict[str, Any], code_checksum: str) -> ExtensionManifest:
    routes = [
        RouteSpec(
            path=str(item["path"]),
            method=str(item.get("method", "GET")).upper(),
            description=str(item.get("description", "")),
        )
        for item in _list_of_dicts(data.get("provides_routes", []), "provides_routes")
    ]
    commands = [
        CommandSpec(
            name=str(item["name"]),
            description=str(item.get("description", "")),
        )
        for item in _list_of_dicts(data.get("provides_commands", []), "provides_commands")
    ]
    return ExtensionManifest(
        id=str(data["id"]),
        name=str(data.get("name") or data["id"]),
        version=str(data.get("version") or "0.0.0"),
        description=str(data.get("description") or ""),
        code_checksum=code_checksum,
        provides_routes=routes,
        provides_commands=commands,
    )


def _list_of_dicts(value: Any, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{field_name} deve essere una lista di oggetti")
    return value


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _normalize_checksum(value: object) -> str:
    if not isinstance(value, str) or not _CHECKSUM_RE.match(value):
        raise ValueError("checksum SHA-256 richiesto")
    lowered = value.lower()
    return lowered if lowered.startswith("sha256:") else f"sha256:{lowered}"


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]+", "_", value)
