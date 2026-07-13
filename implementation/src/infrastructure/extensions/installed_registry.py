# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_CHECKSUM_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")


class ExtensionIntegrityError(Exception):
    """Raised when an extension fails installation integrity checks."""


@dataclass(frozen=True)
class InstalledExtensionEntry:
    extension_id: str
    manifest_checksum: str
    code_checksum: str


class InstalledManifestRegistry:
    """JSON registry of approved extension bundles."""

    def __init__(self, registry_path: str | None = None) -> None:
        self._path = Path(registry_path) if registry_path else None
        self._entries: dict[str, InstalledExtensionEntry] = {}
        if self._path:
            self.reload()

    def reload(self) -> None:
        if not self._path or not self._path.exists():
            logger.warning("InstalledManifestRegistry: registro non trovato %s", self._path)
            self._entries = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error(
                "InstalledManifestRegistry: impossibile leggere %s: %s",
                self._path,
                exc,
            )
            self._entries = {}
            return
        if not isinstance(raw, dict):
            logger.error("InstalledManifestRegistry: il registro deve essere un oggetto JSON")
            self._entries = {}
            return

        entries: dict[str, InstalledExtensionEntry] = {}
        for ext_id, value in raw.items():
            try:
                if not isinstance(value, dict):
                    raise ValueError("entry non strutturata")
                entries[str(ext_id)] = InstalledExtensionEntry(
                    extension_id=str(ext_id),
                    manifest_checksum=_normalize_checksum(value.get("manifest_checksum")),
                    code_checksum=_normalize_checksum(value.get("code_checksum")),
                )
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "InstalledManifestRegistry: entry non valida per %s (%s); estensione disabilitata",
                    ext_id,
                    exc,
                )
        self._entries = entries

    def get_entry(self, ext_id: str) -> InstalledExtensionEntry | None:
        return self._entries.get(ext_id)

    def get_manifest_checksum(self, ext_id: str) -> str | None:
        entry = self._entries.get(ext_id)
        return entry.manifest_checksum if entry else None

    def get_code_checksum(self, ext_id: str) -> str | None:
        entry = self._entries.get(ext_id)
        return entry.code_checksum if entry else None

    def is_approved(self, ext_id: str) -> bool:
        return ext_id in self._entries

    def is_empty(self) -> bool:
        return not self._entries


def _normalize_checksum(value: object) -> str:
    if not isinstance(value, str) or not _CHECKSUM_RE.match(value):
        raise ValueError("checksum SHA-256 richiesto")
    lowered = value.lower()
    return lowered if lowered.startswith("sha256:") else f"sha256:{lowered}"
