# SPDX-License-Identifier: CC-BY-SA-4.0
"""Ingress helpers for converting runtimes into AuthRequest."""

from auth.adapters.ingress.resolvers import (
    AccessTokenCredentialResolver,
    AnonymousResolver,
    AssertedAccountResolver,
    CompositeIdentityResolver,
    SessionCredentialResolver,
)

__all__ = [
    "AccessTokenCredentialResolver",
    "AnonymousResolver",
    "AssertedAccountResolver",
    "CompositeIdentityResolver",
    "SessionCredentialResolver",
]
