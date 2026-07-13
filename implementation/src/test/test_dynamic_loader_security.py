# SPDX-License-Identifier: CC-BY-SA-4.0
"""Regressioni per i loader dinamici: nessun codice non approvato viene eseguito."""
from __future__ import annotations

import hashlib
import json

from src.infrastructure.plugins.loader import PluginLoader
from src.infrastructure.plugins.trust_registry import PluginTrustRegistry
from src.infrastructure.extensions.loader import ExtensionLoader
from src.infrastructure.extensions.installed_registry import InstalledManifestRegistry


def test_plugin_loader_requires_approved_checksum_before_import(tmp_path):
    bundle = tmp_path / "approved"
    bundle.mkdir()
    plugin = bundle / "plugin.py"
    plugin.write_text(
        "from src.domain.plugins import PluginManifest, PluginTrustLevel\n"
        "class Plugin:\n"
        "    manifest = PluginManifest(id='approved', name='approved', version='1', description='', hooks=[], "
        "trust_level=PluginTrustLevel.TRUSTED)\n"
        "    def execute(self, context): pass\n",
        encoding="utf-8",
    )
    code_checksum = "sha256:" + hashlib.sha256(plugin.read_bytes()).hexdigest()
    manifest = bundle / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "id": "approved",
                "name": "approved",
                "version": "1",
                "description": "",
                "hooks": [],
                "trust_level": "TRUSTED",
                "priority": 0,
                "code_checksum": code_checksum,
            }
        ),
        encoding="utf-8",
    )
    manifest_checksum = "sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest()
    registry = tmp_path / "plugins.json"
    registry.write_text(
        json.dumps(
            {
                "approved": {
                    "trust_level": "TRUSTED",
                    "manifest_checksum": manifest_checksum,
                    "code_checksum": code_checksum,
                }
            }
        ),
        encoding="utf-8",
    )

    loader = PluginLoader([str(tmp_path)], PluginTrustRegistry(str(registry)))
    assert [item.manifest.id for item in loader.load_all()] == ["approved"]

    plugin.write_text(plugin.read_text(encoding="utf-8") + "\n# modified\n", encoding="utf-8")
    assert loader.load_all() == []


def test_plugin_loader_skips_unregistered_plugin_before_import(tmp_path):
    marker = tmp_path / "executed"
    bundle = tmp_path / "unregistered"
    bundle.mkdir()
    (bundle / "plugin.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
        "class Plugin: pass\n",
        encoding="utf-8",
    )
    (bundle / "manifest.json").write_text(
        json.dumps({"id": "unregistered", "name": "Unregistered", "code_checksum": "sha256:" + "0" * 64}),
        encoding="utf-8",
    )

    loader = PluginLoader([str(tmp_path)], PluginTrustRegistry(None))
    assert loader.load_all() == []
    assert not marker.exists()


def test_extension_loader_requires_installed_registry_before_import(tmp_path):
    ext_dir = tmp_path / "sample"
    ext_dir.mkdir()
    marker = tmp_path / "executed"
    (ext_dir / "extension.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
        encoding="utf-8",
    )

    loader = ExtensionLoader([str(tmp_path)], InstalledManifestRegistry(None))
    assert loader.load_all() == []
    assert not marker.exists()
