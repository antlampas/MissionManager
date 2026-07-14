# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class RouteSpec:
    path: str
    method: str = "GET"
    description: str = ""


@dataclass(frozen=True)
class CommandSpec:
    name: str
    description: str = ""


@dataclass(frozen=True)
class ExtensionManifest:
    id: str
    name: str
    version: str
    description: str
    code_checksum: str = ""
    provides_routes: list[RouteSpec] = field(default_factory=list)
    provides_commands: list[CommandSpec] = field(default_factory=list)


@dataclass
class ExtensionRequest:
    operator_id: Optional[UUID] = None
    params: dict[str, Any] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
    subject: Any = None


@dataclass(init=False)
class ExtensionResult:
    status_code: int
    body: Any = None
    message: Optional[str] = None

    def __init__(
        self,
        status_code: int,
        body: Any = None,
        message: Optional[str] = None,
        data: Any = None,
    ) -> None:
        self.status_code = status_code
        self.body = data if body is None and data is not None else body
        self.message = message

    @property
    def data(self) -> Any:
        return self.body

    @data.setter
    def data(self, value: Any) -> None:
        self.body = value


@runtime_checkable
class MissionExtension(Protocol):
    manifest: ExtensionManifest

    def execute(self, request: ExtensionRequest) -> ExtensionResult: ...


@runtime_checkable
class HookEmitter(Protocol):
    """Porta con cui un'estensione scatena i propri hook point custom.

    Iniettata dal loader come ``hook_emitter`` nel costruttore, già legata al
    namespace dell'estensione (``BEFORE_EXT:<ext_id>:<evento>`` /
    ``AFTER_EXT:<ext_id>:<evento>``). Gli hook BEFORE_* dei plugin TRUSTED
    possono porre il veto: ``fire_before`` propaga ``OperationAbortedError``
    e l'estensione non deve procedere con l'operazione.
    """

    def fire_before(
        self,
        event: str,
        payload: Optional[dict[str, Any]] = None,
        operator_id: Optional[UUID] = None,
    ) -> Any: ...

    def fire_after(
        self,
        event: str,
        payload: Optional[dict[str, Any]] = None,
        result: Any = None,
        operator_id: Optional[UUID] = None,
    ) -> Any: ...


ExtensionComponent = MissionExtension
