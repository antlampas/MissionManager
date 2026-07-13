# SPDX-License-Identifier: CC-BY-SA-4.0
"""Pure domain model for Auth."""

from auth.domain.account import Account, AccountFlag, AccountKind, AccountStatus
from auth.domain.access_control import (
    AuthorizationContext,
    Decision,
    ResourceRef,
    SubjectRef,
    SubjectType,
    SYSTEM_RESOURCE,
)
from auth.domain.credentials import LocalCredential
from auth.domain.identity import AuthMethod, ExternalIdentity, RequestIdentity
from auth.domain.profile import AuthorizationProfile, Group
from auth.domain.request import AuthRequest, CredentialPresentation
from auth.domain.session import AuthSession
from auth.domain.token import RefreshTokenRecord, TokenPrincipal

__all__ = [
    "Account",
    "AccountFlag",
    "AccountKind",
    "AccountStatus",
    "AuthMethod",
    "AuthRequest",
    "AuthSession",
    "AuthorizationContext",
    "AuthorizationProfile",
    "CredentialPresentation",
    "Decision",
    "ExternalIdentity",
    "Group",
    "LocalCredential",
    "RefreshTokenRecord",
    "RequestIdentity",
    "ResourceRef",
    "SubjectRef",
    "SubjectType",
    "SYSTEM_RESOURCE",
    "TokenPrincipal",
]
