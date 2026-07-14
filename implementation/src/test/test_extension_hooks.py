# SPDX-License-Identifier: CC-BY-SA-4.0
"""Hook point custom delle estensioni: namespace, veto, isolamento dai hook core."""
from __future__ import annotations

import hashlib
import json

import pytest

from src.application.extension_hooks import (
    ExtensionHookEmitter,
    after_hook_name,
    before_hook_name,
    is_extension_hook_name,
)
from src.application.plugin_registry import PluginRegistry
from src.domain.exceptions import OperationAbortedError
from src.domain.plugins import (
    HookContext,
    HookPoint,
    PluginManifest,
    PluginTrustLevel,
)


def _plugin(plugin_id, hooks, trust=PluginTrustLevel.TRUSTED, on_execute=None):
    class _Hook:
        manifest = PluginManifest(
            id=plugin_id,
            name=plugin_id,
            version="1.0.0",
            description="",
            hooks=hooks,
            trust_level=trust,
        )

        def execute(self, context):
            if on_execute is not None:
                on_execute(context)

    return _Hook()


# ---------------------------------------------------------------------------
# Validazione dei nomi
# ---------------------------------------------------------------------------

def test_hook_name_format():
    assert before_hook_name("report", "generate") == "BEFORE_EXT:report:generate"
    assert after_hook_name("report", "generate") == "AFTER_EXT:report:generate"


@pytest.mark.parametrize("name", [
    "BEFORE_EXT:report:generate",
    "AFTER_EXT:mission-stats:compute",
    "BEFORE_EXT:a1:b_2.c-3",
])
def test_valid_extension_hook_names(name):
    assert is_extension_hook_name(name)


@pytest.mark.parametrize("name", [
    "BEFORE_CREATE_MISSION",        # hook core, non custom
    "BEFORE_EXT:",                  # namespace incompleto
    "BEFORE_EXT:report",            # manca l'evento
    "EXT:report:generate",          # manca BEFORE/AFTER
    "BEFORE_EXT:re port:x",         # spazio nell'id
    "BEFORE_EXT::generate",         # id vuoto
    "before_ext:report:generate",   # case sbagliato
    123,                            # non stringa
])
def test_invalid_extension_hook_names(name):
    assert not is_extension_hook_name(name)


def test_emitter_rejects_invalid_event_names():
    emitter = ExtensionHookEmitter(PluginRegistry(), "report")
    with pytest.raises(ValueError, match="evento"):
        emitter.fire_before("con:due punti")
    with pytest.raises(ValueError, match="evento"):
        emitter.fire_after("")


def test_emitter_rejects_unsafe_extension_id():
    with pytest.raises(ValueError, match="namespace"):
        ExtensionHookEmitter(PluginRegistry(), "bad:id")


# ---------------------------------------------------------------------------
# Semantica di esecuzione
# ---------------------------------------------------------------------------

def test_fire_before_trusted_plugin_can_veto():
    def _veto(context):
        context.abort = True
        context.user_message = "operazione vietata"

    registry = PluginRegistry()
    registry.register(_plugin("veto", ["BEFORE_EXT:report:generate"], on_execute=_veto))
    emitter = ExtensionHookEmitter(registry, "report")
    with pytest.raises(OperationAbortedError, match="operazione vietata"):
        emitter.fire_before("generate", {"k": "v"})


def test_fire_before_sandboxed_plugin_cannot_veto():
    def _try_veto(context):
        context.abort = True

    registry = PluginRegistry()
    registry.register(_plugin(
        "sandboxed", ["BEFORE_EXT:report:generate"],
        trust=PluginTrustLevel.SANDBOXED, on_execute=_try_veto,
    ))
    emitter = ExtensionHookEmitter(registry, "report")
    ctx = emitter.fire_before("generate")
    assert ctx is not None and ctx.abort is False


def test_fire_after_receives_payload_and_result():
    seen = {}

    def _record(context):
        seen["hook"] = context.hook_point
        seen["payload"] = dict(context.payload)
        seen["result"] = context.result

    registry = PluginRegistry()
    registry.register(_plugin("obs", ["AFTER_EXT:report:generate"], on_execute=_record))
    emitter = ExtensionHookEmitter(registry, "report")
    emitter.fire_after("generate", {"k": "v"}, result={"total": 3})
    assert seen == {
        "hook": "AFTER_EXT:report:generate",
        "payload": {"k": "v"},
        "result": {"total": 3},
    }


def test_fire_after_swallows_plugin_exceptions():
    def _boom(context):
        raise RuntimeError("hook rotto")

    registry = PluginRegistry()
    registry.register(_plugin("boom", ["AFTER_EXT:report:generate"], on_execute=_boom))
    emitter = ExtensionHookEmitter(registry, "report")
    emitter.fire_after("generate")  # non deve sollevare


def test_emitter_without_registry_is_noop():
    emitter = ExtensionHookEmitter(None, "report")
    assert emitter.fire_before("generate") is None
    assert emitter.fire_after("generate") is None


def test_string_hook_cannot_intercept_core_enum_fires():
    """Un plugin registrato sulla stringa "BEFORE_UPDATE_STATUS" non deve
    intercettare i flussi core, che scatenano i membri dell'enum."""
    calls = []
    registry = PluginRegistry()
    registry.register(_plugin(
        "impostor", ["BEFORE_UPDATE_STATUS"], on_execute=lambda c: calls.append(1)
    ))
    registry.fire(
        HookPoint.BEFORE_UPDATE_STATUS,
        HookContext(hook_point=HookPoint.BEFORE_UPDATE_STATUS),
    )
    assert calls == []


# ---------------------------------------------------------------------------
# Manifest dei plugin: hook custom accettati, refusi rifiutati
# ---------------------------------------------------------------------------

def _write_plugin_bundle(tmp_path, hooks):
    bundle = tmp_path / "p"
    bundle.mkdir()
    code = "class Plugin:\n    def execute(self, c): pass\n"
    (bundle / "plugin.py").write_text(code)
    code_checksum = "sha256:" + hashlib.sha256(code.encode()).hexdigest()
    manifest = {"id": "p", "hooks": hooks, "code_checksum": code_checksum}
    raw = json.dumps(manifest).encode()
    (bundle / "manifest.json").write_bytes(raw)
    manifest_checksum = "sha256:" + hashlib.sha256(raw).hexdigest()
    registry_file = tmp_path / "reg.json"
    registry_file.write_text(json.dumps({
        "p": {
            "trust_level": "TRUSTED",
            "manifest_checksum": manifest_checksum,
            "code_checksum": code_checksum,
        }
    }))
    return registry_file


def test_plugin_loader_accepts_extension_hook_names(tmp_path):
    from src.infrastructure.plugins.loader import PluginLoader
    from src.infrastructure.plugins.trust_registry import PluginTrustRegistry

    registry_file = _write_plugin_bundle(
        tmp_path, ["AFTER_CREATE_MISSION", "BEFORE_EXT:report:generate"]
    )
    loader = PluginLoader([str(tmp_path)], PluginTrustRegistry(str(registry_file)))
    plugins = loader.load_all()
    assert len(plugins) == 1
    assert plugins[0].manifest.hooks == [
        HookPoint.AFTER_CREATE_MISSION, "BEFORE_EXT:report:generate"
    ]


def test_plugin_loader_rejects_malformed_hook_names(tmp_path):
    from src.infrastructure.plugins.loader import PluginLoader
    from src.infrastructure.plugins.trust_registry import PluginTrustRegistry

    registry_file = _write_plugin_bundle(tmp_path, ["BEFORE_EXT:report"])
    loader = PluginLoader([str(tmp_path)], PluginTrustRegistry(str(registry_file)))
    assert loader.load_all() == []
