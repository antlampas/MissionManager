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

from ...application.plugin_registry import PluginRegistry
from ...domain.plugins import HookPoint, MissionHook, PluginManifest, PluginTrustLevel
from .trust_registry import PluginTrustRegistry

logger = logging.getLogger(__name__)

_CHECKSUM_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")


class PluginLoader:
    """Load approved plugin bundles."""

    def __init__(
        self,
        scan_paths: list[str],
        trust_registry: PluginTrustRegistry,
    ) -> None:
        self._scan_paths = scan_paths
        self._trust = trust_registry

    def load_all(self) -> list[MissionHook]:
        if not self._scan_paths:
            logger.debug("PluginLoader: nessun percorso plugin configurato")
            return []
        if self._trust.is_empty():
            logger.warning(
                "PluginLoader: PluginTrustRegistry vuoto o assente; nessun plugin caricato"
            )
            return []

        plugins: list[MissionHook] = []
        for bundle_dir in self._bundle_dirs():
            plugin = self._load_bundle(bundle_dir)
            if plugin is not None:
                plugins.append(plugin)
        return plugins

    def load_into(self, registry: PluginRegistry) -> None:
        for plugin in self.load_all():
            registry.register(plugin)

    def _bundle_dirs(self) -> list[Path]:
        bundles: list[Path] = []
        for raw_path in self._scan_paths:
            scan_dir = Path(raw_path)
            if not scan_dir.is_dir():
                logger.warning("PluginLoader: directory non trovata %s", raw_path)
                continue
            if (scan_dir / "manifest.json").is_file() and (scan_dir / "plugin.py").is_file():
                bundles.append(scan_dir)
                continue
            for child in sorted(scan_dir.iterdir()):
                if (
                    child.is_dir()
                    and (child / "manifest.json").is_file()
                    and (child / "plugin.py").is_file()
                ):
                    bundles.append(child)
        return bundles

    def _load_bundle(self, bundle_dir: Path) -> MissionHook | None:
        manifest_path = bundle_dir / "manifest.json"
        code_path = bundle_dir / "plugin.py"
        try:
            manifest_raw = manifest_path.read_bytes()
            manifest_data = json.loads(manifest_raw.decode("utf-8"))
        except Exception as exc:
            logger.error("PluginLoader: manifest non valido in %s: %s", bundle_dir, exc)
            return None
        if not isinstance(manifest_data, dict):
            logger.error("PluginLoader: manifest non oggetto in %s", bundle_dir)
            return None

        plugin_id = str(manifest_data.get("id") or "")
        if not plugin_id:
            logger.error("PluginLoader: manifest senza id in %s", bundle_dir)
            return None
        entry = self._trust.get_entry(plugin_id)
        if entry is None:
            logger.error("PluginLoader: plugin %s non approvato", plugin_id)
            return None

        actual_manifest_checksum = _sha256_bytes(manifest_raw)
        if actual_manifest_checksum != entry.manifest_checksum:
            logger.error("PluginLoader: manifest checksum non valido per %s", plugin_id)
            return None

        actual_code_checksum = _sha256_file(code_path)
        try:
            declared_code_checksum = _normalize_checksum(
                manifest_data.get("code_checksum") or entry.code_checksum
            )
        except ValueError as exc:
            logger.error("PluginLoader: code_checksum non valido per %s: %s", plugin_id, exc)
            return None
        if actual_code_checksum != entry.code_checksum or declared_code_checksum != entry.code_checksum:
            logger.error("PluginLoader: code checksum non valido per %s", plugin_id)
            return None

        try:
            manifest = _manifest_from_data(
                manifest_data,
                trust_level=entry.trust_level,
                code_checksum=entry.code_checksum,
            )
        except ValueError as exc:
            logger.error("PluginLoader: manifest non valido per %s: %s", plugin_id, exc)
            return None

        module = self._import_module(code_path, plugin_id, actual_code_checksum)
        if module is None:
            return None
        plugin_class = getattr(module, "Plugin", None)
        if plugin_class is None:
            logger.error("PluginLoader: classe Plugin non trovata in %s", code_path)
            return None
        try:
            inner = _instantiate_plugin(plugin_class, manifest)
        except Exception as exc:
            logger.error("PluginLoader: impossibile istanziare %s: %s", plugin_id, exc)
            return None
        return _LoadedPlugin(inner, manifest)

    @staticmethod
    def _import_module(code_path: Path, plugin_id: str, checksum: str) -> Any | None:
        module_name = f"plugin_{_safe_name(plugin_id)}_{checksum[-12:]}"
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
            logger.error("PluginLoader: impossibile importare %s: %s", code_path, exc)
            return None


class _LoadedPlugin:
    def __init__(self, inner: Any, manifest: PluginManifest) -> None:
        self._inner = inner
        self._manifest = manifest

    @property
    def manifest(self) -> PluginManifest:
        return self._manifest

    def execute(self, context) -> None:
        self._inner.execute(context)


def _instantiate_plugin(plugin_class: type, manifest: PluginManifest) -> Any:
    try:
        signature = inspect.signature(plugin_class)
    except (TypeError, ValueError):
        signature = None
    if signature is not None:
        params = signature.parameters
        accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        if "manifest" in params or accepts_kwargs:
            return plugin_class(manifest=manifest)
    return plugin_class()


def _manifest_from_data(
    data: dict[str, Any],
    trust_level: PluginTrustLevel,
    code_checksum: str,
) -> PluginManifest:
    hooks_raw = data.get("hooks", [])
    if not isinstance(hooks_raw, list) or not all(isinstance(item, str) for item in hooks_raw):
        raise ValueError("hooks deve essere una lista di stringhe")
    hooks: list[HookPoint] = []
    for hook_name in hooks_raw:
        try:
            hooks.append(HookPoint(hook_name))
        except ValueError as exc:
            raise ValueError(f"hook sconosciuto: {hook_name}") from exc
    priority = int(data.get("priority", 0))
    return PluginManifest(
        id=str(data["id"]),
        name=str(data.get("name") or data["id"]),
        version=str(data.get("version") or "0.0.0"),
        description=str(data.get("description") or ""),
        hooks=hooks,
        trust_level=trust_level,
        priority=priority,
        code_checksum=code_checksum,
    )


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
