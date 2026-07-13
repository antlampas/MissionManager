# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ...domain.plugins import PluginTrustLevel

logger = logging.getLogger(__name__)

_CHECKSUM_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class PluginTrustEntry:
    plugin_id: str
    trust_level: PluginTrustLevel
    manifest_checksum: str
    code_checksum: str


class PluginTrustRegistry:
    """JSON registry of approved plugin bundles."""

    def __init__(self, registry_path: str | None = None) -> None:
        self._path = Path(registry_path) if registry_path else None
        self._entries: dict[str, PluginTrustEntry] = {}
        if self._path:
            self.reload()

    def reload(self) -> None:
        if not self._path or not self._path.exists():
            logger.warning("PluginTrustRegistry: registro non trovato %s", self._path)
            self._entries = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "PluginTrustRegistry: impossibile leggere %s: %s", self._path, exc
            )
            self._entries = {}
            return
        if not isinstance(raw, dict):
            logger.warning("PluginTrustRegistry: il registro deve essere un oggetto JSON")
            self._entries = {}
            return

        entries: dict[str, PluginTrustEntry] = {}
        for plugin_id, value in raw.items():
            try:
                if not isinstance(value, dict):
                    raise ValueError("entry non strutturata")
                level = PluginTrustLevel(value.get("trust_level", "SANDBOXED"))
                manifest_checksum = _normalize_checksum(value.get("manifest_checksum"))
                code_checksum = _normalize_checksum(value.get("code_checksum"))
                entries[str(plugin_id)] = PluginTrustEntry(
                    plugin_id=str(plugin_id),
                    trust_level=level,
                    manifest_checksum=manifest_checksum,
                    code_checksum=code_checksum,
                )
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "PluginTrustRegistry: entry non valida per %s (%s); plugin disabilitato",
                    plugin_id,
                    exc,
                )
        self._entries = entries

    def get(self, plugin_id: str) -> PluginTrustLevel | None:
        entry = self._entries.get(plugin_id)
        return entry.trust_level if entry else None

    def get_level(self, plugin_id: str) -> PluginTrustLevel | None:
        return self.get(plugin_id)

    def get_entry(self, plugin_id: str) -> PluginTrustEntry | None:
        return self._entries.get(plugin_id)

    def has_entry(self, plugin_id: str) -> bool:
        return plugin_id in self._entries

    def is_empty(self) -> bool:
        return not self._entries

    def plugin_id_for_manifest_checksum(self, checksum: str) -> str | None:
        checksum = _normalize_checksum(checksum)
        for plugin_id, entry in self._entries.items():
            if entry.manifest_checksum == checksum:
                return plugin_id
        return None


class TrustRegistry(PluginTrustRegistry):
    """Alias omogeneo con PhotoGallery."""


def _normalize_checksum(value: object) -> str:
    if not isinstance(value, str) or not _CHECKSUM_RE.match(value):
        raise ValueError("checksum SHA-256 richiesto")
    lowered = value.lower()
    return lowered if lowered.startswith("sha256:") else f"sha256:{lowered}"
