# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import UUID


class HookPoint(Enum):
    """Punti di aggancio dei plugin sui flussi mutanti del dominio.

    Gli hook specifici (CREATE_MISSION, CREATE_ASSIGNMENT, …) coprono le
    operazioni con payload proprio; gli hook generici (UPDATE_STATUS, ASSIGN,
    DELETE) coprono più tipi di entità e portano ``entity_type`` nel payload.
    I sottosistemi di sicurezza (ACL, autenticazione, profili) non espongono
    hook per progetto: non sono delegabili ai plugin (anti-escalation).
    """

    BEFORE_CREATE_MISSION = "BEFORE_CREATE_MISSION"
    AFTER_CREATE_MISSION = "AFTER_CREATE_MISSION"
    BEFORE_CREATE_ASSIGNMENT = "BEFORE_CREATE_ASSIGNMENT"
    AFTER_CREATE_ASSIGNMENT = "AFTER_CREATE_ASSIGNMENT"
    BEFORE_UPDATE_STATUS = "BEFORE_UPDATE_STATUS"
    AFTER_UPDATE_STATUS = "AFTER_UPDATE_STATUS"
    BEFORE_AWARD_BADGE = "BEFORE_AWARD_BADGE"
    AFTER_AWARD_BADGE = "AFTER_AWARD_BADGE"
    # Assegnazioni: payload {entity_type: ASSIGNMENT|ACTIVITY, entity_id,
    # action: ASSIGN|UNASSIGN, assignee_type?, assignee_id?, person_id?}
    BEFORE_ASSIGN = "BEFORE_ASSIGN"
    AFTER_ASSIGN = "AFTER_ASSIGN"
    # Cancellazioni: payload {entity_type: MISSION|ASSIGNMENT|PERSON|GROUP, entity_id}
    BEFORE_DELETE = "BEFORE_DELETE"
    AFTER_DELETE = "AFTER_DELETE"
    BEFORE_CREATE_BADGE = "BEFORE_CREATE_BADGE"
    AFTER_CREATE_BADGE = "AFTER_CREATE_BADGE"
    BEFORE_CREATE_PERSON = "BEFORE_CREATE_PERSON"
    AFTER_CREATE_PERSON = "AFTER_CREATE_PERSON"
    BEFORE_UPDATE_PERSON = "BEFORE_UPDATE_PERSON"
    AFTER_UPDATE_PERSON = "AFTER_UPDATE_PERSON"
    BEFORE_CREATE_GROUP = "BEFORE_CREATE_GROUP"
    AFTER_CREATE_GROUP = "AFTER_CREATE_GROUP"
    BEFORE_UPDATE_GROUP = "BEFORE_UPDATE_GROUP"
    AFTER_UPDATE_GROUP = "AFTER_UPDATE_GROUP"
    # Membership dei gruppi: payload {group_id, person_id, action: ADD|REMOVE}
    BEFORE_MANAGE_MEMBERS = "BEFORE_MANAGE_MEMBERS"
    AFTER_MANAGE_MEMBERS = "AFTER_MANAGE_MEMBERS"


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
