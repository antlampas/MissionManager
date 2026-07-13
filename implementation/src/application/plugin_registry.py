# SPDX-License-Identifier: CC-BY-SA-4.0
"""Plugin registry with trust-level enforcement and priority ordering.

TRUSTED plugins receive the real HookContext and can mutate result/abort.
SANDBOXED plugins receive a defensive copy; any mutations to `result` are
ignored and they cannot set abort=True (the flag is discarded).

Plugins within the same hook point are executed in descending priority order
(higher priority number = runs first).
"""
import logging
import copy
from collections import defaultdict
from typing import Any

from ..domain.exceptions import OperationAbortedError
from ..domain.plugins import (
    HookContext,
    HookPoint,
    MissionHook,
    PluginManifest,
    PluginTrustLevel,
    ScopedHookContext,
)

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registro dei plugin hook con trust levels e ordinamento per priorità."""

    def __init__(self, trust_registry: Any | None = None) -> None:
        self._trust = trust_registry
        self._hooks: dict[HookPoint | str, list[MissionHook]] = defaultdict(list)

    def register(self, hook: MissionHook) -> None:
        if self._trust is not None and self._registered_trust(hook.manifest.id) is None:
            raise ValueError(f"Plugin non presente nel TrustRegistry: {hook.manifest.id}")
        for point in hook.manifest.hooks:
            self._hooks[point].append(hook)
        for point in hook.manifest.hooks:
            self._hooks[point].sort(key=lambda h: h.manifest.priority, reverse=True)

    def unregister(self, plugin_id: str) -> None:
        for point in list(self._hooks.keys()):
            self._hooks[point] = [
                h for h in self._hooks[point] if h.manifest.id != plugin_id
            ]

    def fire(self, point: HookPoint | str, context: HookContext) -> HookContext:
        hooks = self._hooks.get(point, [])
        if not hooks:
            return context
        is_before = _hook_name(point).startswith("BEFORE_")
        for hook in hooks:
            trusted = self._effective_trust(hook) == PluginTrustLevel.TRUSTED
            ctx_to_pass = context if trusted else self._scoped_context(context)

            try:
                hook.execute(ctx_to_pass)
            except Exception:
                if is_before and trusted:
                    raise
                logger.exception(
                    "Hook '%s' ha sollevato un'eccezione durante %s",
                    hook.manifest.id,
                    _hook_name(point),
                )
                continue

            if not trusted:
                if getattr(ctx_to_pass, "abort", False):
                    logger.warning(
                        "Plugin sandboxed '%s' ha tentato di impostare abort=True su %s, ignorato",
                        hook.manifest.id,
                        _hook_name(point),
                    )
                continue

            if is_before and context.abort:
                break

        if is_before and context.abort:
            raise OperationAbortedError(
                context.user_message or "Operazione annullata da un plugin",
                abort_reason=context.abort_reason,
            )
        return context

    def list_plugins(self) -> list[PluginManifest]:
        seen: set[str] = set()
        result: list[PluginManifest] = []
        for hooks in self._hooks.values():
            for hook in hooks:
                plugin_id = hook.manifest.id
                if plugin_id not in seen:
                    seen.add(plugin_id)
                    result.append(hook.manifest)
        return result

    def _registered_trust(self, plugin_id: str) -> PluginTrustLevel | None:
        if self._trust is None:
            return None
        if hasattr(self._trust, "get_level"):
            return self._trust.get_level(plugin_id)
        if hasattr(self._trust, "get"):
            return self._trust.get(plugin_id)
        return None

    def _effective_trust(self, hook: MissionHook) -> PluginTrustLevel:
        registered = self._registered_trust(hook.manifest.id)
        if registered is not None:
            return registered
        return hook.manifest.trust_level

    @staticmethod
    def _scoped_context(context: HookContext) -> ScopedHookContext:
        payload = _safe_copy(context.payload)
        for sensitive_key in ("content", "raw_content", "file_bytes"):
            payload.pop(sensitive_key, None)
        return ScopedHookContext(
            hook_point=context.hook_point,
            operator_id=context.operator_id,
            payload=payload,
            result=_safe_copy(context.result),
            subject=context.subject,
            abort=False,
            abort_reason=None,
            user_message=None,
        )


def _hook_name(point: HookPoint | str) -> str:
    return getattr(point, "value", str(point))


def _safe_copy(value: Any) -> Any:
    try:
        return copy.deepcopy(value)
    except Exception:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            return list(value)
        return value
