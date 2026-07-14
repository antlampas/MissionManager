# SPDX-License-Identifier: CC-BY-SA-4.0
"""Semantica del PluginRegistry: trust level, priorità, abort, isolamento sandbox."""
from __future__ import annotations

import pytest

from src.application.plugin_registry import PluginRegistry
from src.domain.exceptions import OperationAbortedError
from src.domain.plugins import (
    HookContext,
    HookPoint,
    PluginManifest,
    PluginTrustLevel,
)


def _plugin(plugin_id, hooks, trust=PluginTrustLevel.TRUSTED, priority=0, on_execute=None):
    class _Hook:
        manifest = PluginManifest(
            id=plugin_id,
            name=plugin_id,
            version="1.0.0",
            description="",
            hooks=hooks,
            trust_level=trust,
            priority=priority,
        )

        def execute(self, context):
            if on_execute is not None:
                on_execute(context)

    return _Hook()


def test_fire_orders_by_priority_desc():
    order = []
    registry = PluginRegistry()
    registry.register(_plugin("low", [HookPoint.AFTER_CREATE_MISSION], priority=1,
                              on_execute=lambda c: order.append("low")))
    registry.register(_plugin("high", [HookPoint.AFTER_CREATE_MISSION], priority=99,
                              on_execute=lambda c: order.append("high")))
    registry.fire(
        HookPoint.AFTER_CREATE_MISSION,
        HookContext(hook_point=HookPoint.AFTER_CREATE_MISSION),
    )
    assert order == ["high", "low"]


def test_duplicate_registration_rejected():
    registry = PluginRegistry()
    plugin = _plugin("dup", [HookPoint.AFTER_CREATE_MISSION])
    registry.register(plugin)
    with pytest.raises(ValueError, match="già registrato"):
        registry.register(plugin)


def test_unregister_allows_re_registration():
    calls = []
    registry = PluginRegistry()
    plugin = _plugin("re", [HookPoint.AFTER_CREATE_MISSION],
                     on_execute=lambda c: calls.append(1))
    registry.register(plugin)
    registry.unregister("re")
    registry.fire(
        HookPoint.AFTER_CREATE_MISSION,
        HookContext(hook_point=HookPoint.AFTER_CREATE_MISSION),
    )
    assert calls == []
    registry.register(plugin)
    registry.fire(
        HookPoint.AFTER_CREATE_MISSION,
        HookContext(hook_point=HookPoint.AFTER_CREATE_MISSION),
    )
    assert calls == [1]


def test_trusted_before_hook_abort_raises_and_stops_chain():
    executed = []

    def _abort(context):
        executed.append("abort")
        context.abort = True
        context.abort_reason = "veto"
        context.user_message = "operazione vietata"

    registry = PluginRegistry()
    registry.register(_plugin("veto", [HookPoint.BEFORE_CREATE_MISSION], priority=10,
                              on_execute=_abort))
    registry.register(_plugin("later", [HookPoint.BEFORE_CREATE_MISSION], priority=0,
                              on_execute=lambda c: executed.append("later")))
    with pytest.raises(OperationAbortedError, match="operazione vietata"):
        registry.fire(
            HookPoint.BEFORE_CREATE_MISSION,
            HookContext(hook_point=HookPoint.BEFORE_CREATE_MISSION),
        )
    assert executed == ["abort"]


def test_sandboxed_hook_cannot_abort_or_mutate_context():
    def _try_tamper(context):
        context.abort = True
        context.abort_reason = "tentativo"
        context.result["injected"] = True
        context.payload["injected"] = True

    registry = PluginRegistry()
    registry.register(_plugin("sandboxed", [HookPoint.BEFORE_CREATE_MISSION],
                              trust=PluginTrustLevel.SANDBOXED, on_execute=_try_tamper))
    ctx = HookContext(
        hook_point=HookPoint.BEFORE_CREATE_MISSION,
        payload={"title": "Op"},
    )
    registry.fire(HookPoint.BEFORE_CREATE_MISSION, ctx)
    assert ctx.abort is False
    assert ctx.result == {}
    assert ctx.payload == {"title": "Op"}


def test_sandboxed_hook_receives_subject_copy():
    seen = {}

    def _mutate_subject(context):
        seen["subject"] = context.subject
        context.subject["tampered"] = True

    registry = PluginRegistry()
    registry.register(_plugin("sandboxed", [HookPoint.AFTER_CREATE_MISSION],
                              trust=PluginTrustLevel.SANDBOXED, on_execute=_mutate_subject))
    subject = {"name": "original"}
    ctx = HookContext(hook_point=HookPoint.AFTER_CREATE_MISSION, subject=subject)
    registry.fire(HookPoint.AFTER_CREATE_MISSION, ctx)
    assert seen["subject"] == {"name": "original", "tampered": True}
    assert subject == {"name": "original"}


def test_sandboxed_payload_drops_sensitive_keys():
    seen = {}

    def _record(context):
        seen["payload"] = dict(context.payload)

    registry = PluginRegistry()
    registry.register(_plugin("sandboxed", [HookPoint.AFTER_CREATE_MISSION],
                              trust=PluginTrustLevel.SANDBOXED, on_execute=_record))
    ctx = HookContext(
        hook_point=HookPoint.AFTER_CREATE_MISSION,
        payload={"title": "Op", "content": b"segreto", "raw_content": "x", "file_bytes": b"y"},
    )
    registry.fire(HookPoint.AFTER_CREATE_MISSION, ctx)
    assert seen["payload"] == {"title": "Op"}


def test_after_hook_exception_is_swallowed():
    def _boom(context):
        raise RuntimeError("hook rotto")

    registry = PluginRegistry()
    registry.register(_plugin("boom", [HookPoint.AFTER_CREATE_MISSION], on_execute=_boom))
    ctx = HookContext(hook_point=HookPoint.AFTER_CREATE_MISSION)
    registry.fire(HookPoint.AFTER_CREATE_MISSION, ctx)  # non deve sollevare


def test_before_trusted_exception_propagates():
    def _boom(context):
        raise RuntimeError("hook rotto")

    registry = PluginRegistry()
    registry.register(_plugin("boom", [HookPoint.BEFORE_CREATE_MISSION], on_execute=_boom))
    with pytest.raises(RuntimeError):
        registry.fire(
            HookPoint.BEFORE_CREATE_MISSION,
            HookContext(hook_point=HookPoint.BEFORE_CREATE_MISSION),
        )


def test_before_sandboxed_exception_is_swallowed():
    def _boom(context):
        raise RuntimeError("hook rotto")

    registry = PluginRegistry()
    registry.register(_plugin("boom", [HookPoint.BEFORE_CREATE_MISSION],
                              trust=PluginTrustLevel.SANDBOXED, on_execute=_boom))
    ctx = HookContext(hook_point=HookPoint.BEFORE_CREATE_MISSION)
    registry.fire(HookPoint.BEFORE_CREATE_MISSION, ctx)  # non deve sollevare


def test_trust_registry_overrides_manifest_trust():
    """Il TrustRegistry è autoritativo: un manifest TRUSTED con registro
    SANDBOXED viene eseguito in sandbox (mutazioni ignorate)."""

    class _FakeTrust:
        def get_level(self, plugin_id):
            return PluginTrustLevel.SANDBOXED

    def _try_abort(context):
        context.abort = True

    registry = PluginRegistry(_FakeTrust())
    registry.register(_plugin("declared-trusted", [HookPoint.BEFORE_CREATE_MISSION],
                              trust=PluginTrustLevel.TRUSTED, on_execute=_try_abort))
    ctx = HookContext(hook_point=HookPoint.BEFORE_CREATE_MISSION)
    registry.fire(HookPoint.BEFORE_CREATE_MISSION, ctx)
    assert ctx.abort is False


def test_register_requires_trust_entry_when_registry_present():
    class _EmptyTrust:
        def get_level(self, plugin_id):
            return None

    registry = PluginRegistry(_EmptyTrust())
    with pytest.raises(ValueError, match="TrustRegistry"):
        registry.register(_plugin("unknown", [HookPoint.AFTER_CREATE_MISSION]))


def test_list_plugins_deduplicates_ids():
    registry = PluginRegistry()
    registry.register(_plugin(
        "multi", [HookPoint.AFTER_CREATE_MISSION, HookPoint.AFTER_CREATE_ASSIGNMENT]
    ))
    assert [m.id for m in registry.list_plugins()] == ["multi"]
