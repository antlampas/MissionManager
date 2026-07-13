# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import UUID


class HookPoint(Enum):
    BEFORE_CREATE_MISSION = "BEFORE_CREATE_MISSION"
    AFTER_CREATE_MISSION = "AFTER_CREATE_MISSION"
    BEFORE_CREATE_ASSIGNMENT = "BEFORE_CREATE_ASSIGNMENT"
    AFTER_CREATE_ASSIGNMENT = "AFTER_CREATE_ASSIGNMENT"
    BEFORE_UPDATE_STATUS = "BEFORE_UPDATE_STATUS"
    AFTER_UPDATE_STATUS = "AFTER_UPDATE_STATUS"
    BEFORE_AWARD_BADGE = "BEFORE_AWARD_BADGE"
    AFTER_AWARD_BADGE = "AFTER_AWARD_BADGE"


class PluginTrustLevel(str, Enum):
    """Execution sandbox level for a plugin.

    TRUSTED: the plugin receives the real HookContext and can mutate result/abort.
    SANDBOXED: the plugin receives a defensive copy; writes to result are ignored.
    """
    TRUSTED = "TRUSTED"
    SANDBOXED = "SANDBOXED"


@dataclass(frozen=True)
class PluginManifest:
    id: str
    name: str
    version: str
    description: str
    hooks: list[HookPoint | str]
    trust_level: PluginTrustLevel = PluginTrustLevel.SANDBOXED
    priority: int = 0  # higher priority → executed first
    code_checksum: str = ""


@dataclass
class HookContext:
    hook_point: HookPoint | str
    operator_id: Optional[UUID] = None
    payload: dict[str, Any] = field(default_factory=dict)
    result: Any = field(default_factory=dict)
    subject: Any = None
    abort: bool = False
    abort_reason: Optional[str] = None
    user_message: Optional[str] = None


@dataclass
class ScopedHookContext:
    hook_point: HookPoint | str
    operator_id: Optional[UUID] = None
    payload: dict[str, Any] = field(default_factory=dict)
    result: Any = field(default_factory=dict)
    subject: Any = None
    abort: bool = False
    abort_reason: Optional[str] = None
    user_message: Optional[str] = None


@runtime_checkable
class MissionHook(Protocol):
    @property
    def manifest(self) -> PluginManifest: ...

    def execute(self, context: HookContext) -> None: ...


PluginHook = MissionHook
