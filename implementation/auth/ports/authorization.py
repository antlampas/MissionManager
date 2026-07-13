# SPDX-License-Identifier: CC-BY-SA-4.0
"""Authorization and ingress-resolution ports."""

from __future__ import annotations

from typing import Protocol

from auth.domain.access_control import (
    AccessControlModelExtension,
    OperationSpec,
    ResourceRef,
    SubjectRef,
)
from auth.domain.identity import RequestIdentity
from auth.domain.profile import AuthorizationProfile
from auth.domain.request import AuthRequest
from auth.domain.types import AccountId


class IdentityResolver(Protocol):
    def resolve(self, request: AuthRequest) -> RequestIdentity: ...


class ProfileProvider(Protocol):
    def profile_of(self, subject: SubjectRef) -> AuthorizationProfile: ...


class AccessControlModelRegistry(Protocol):
    def active(self) -> AccessControlModelExtension: ...

    def get(self, model_id: str) -> AccessControlModelExtension | None: ...

    def register(self, model: AccessControlModelExtension) -> None: ...


class AccessControlExtensionProvider(Protocol):
    id: str

    def capability(self, name: str) -> object: ...


class OperationCatalog(Protocol):
    def get(self, operation: str) -> OperationSpec: ...


class PrincipalBindingPort(Protocol):
    def bind(self, account_id: AccountId) -> object | None: ...
