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


ExtensionComponent = MissionExtension
