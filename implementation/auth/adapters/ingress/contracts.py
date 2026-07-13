# SPDX-License-Identifier: CC-BY-SA-4.0
"""Contracts for consumer ingress adapters."""

from __future__ import annotations

from typing import Protocol

from auth.application.dtos import RequestOutcome
from auth.domain.identity import RequestIdentity
from auth.domain.request import AuthRequest, CredentialPresentation


class RequestNormalizer(Protocol):
    def normalize(self, raw_input: object) -> AuthRequest: ...


class OutcomeTranslator(Protocol):
    def translate(self, outcome: RequestOutcome) -> object: ...


class CredentialResolver(Protocol):
    def supports(self, credential: CredentialPresentation) -> bool: ...

    def resolve(self, request: AuthRequest, credential: CredentialPresentation) -> RequestIdentity | None: ...
