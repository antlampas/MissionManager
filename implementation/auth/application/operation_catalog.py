# SPDX-License-Identifier: CC-BY-SA-4.0
"""Operation catalog used by the request gateway and authorization service."""

from __future__ import annotations

from auth.domain.access_control import OperationSpec
from auth.domain.errors import ValidationError


class StaticOperationCatalog:
    def __init__(self, operations: dict[str, OperationSpec] | None = None) -> None:
        self._operations: dict[str, OperationSpec] = dict(operations or {})

    def register(self, spec: OperationSpec) -> None:
        self._operations[spec.name] = spec

    def get(self, operation: str) -> OperationSpec:
        try:
            return self._operations[operation]
        except KeyError as exc:
            raise ValidationError(f"unknown operation: {operation}") from exc

    @classmethod
    def with_defaults(cls) -> StaticOperationCatalog:
        catalog = cls()
        for spec in (
            OperationSpec("VIEW", read_only=True),
            OperationSpec("EDIT", read_only=False),
            OperationSpec("EXECUTE", read_only=False),
            OperationSpec("MANAGE_ACCOUNTS", read_only=False, inheritable=False, protected=True),
            OperationSpec("MANAGE_PROFILES", read_only=False, inheritable=False, protected=True),
            OperationSpec("MANAGE_CREDENTIALS", read_only=False, inheritable=False, protected=True),
            OperationSpec("MANAGE_ACCESS_CONTROL", read_only=False, inheritable=False, protected=True),
        ):
            catalog.register(spec)
        return catalog
