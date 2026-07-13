# SPDX-License-Identifier: CC-BY-SA-4.0
"""Composable credential resolvers used by RequestGateway."""

from __future__ import annotations

from auth.adapters.ingress.contracts import CredentialResolver
from auth.application.session_service import SessionService
from auth.application.token_service import TokenService
from auth.domain.access_control import SubjectRef
from auth.domain.errors import AuthenticationError, ValidationError
from auth.domain.identity import AuthMethod, RequestIdentity
from auth.domain.request import AuthRequest, CredentialKind, CredentialPresentation
from auth.domain.types import AccountId, SessionId
from auth.ports.repositories import AccountRepository
from auth.ports.security import Clock


class CompositeIdentityResolver:
    def __init__(self, resolvers: list[CredentialResolver]) -> None:
        self._resolvers = resolvers

    def resolve(self, request: AuthRequest) -> RequestIdentity:
        for credential in request.credential_presentations:
            for resolver in self._resolvers:
                if resolver.supports(credential):
                    identity = resolver.resolve(request, credential)
                    if identity is not None:
                        return identity
        if request.protection.allow_anonymous:
            return RequestIdentity.anonymous()
        raise AuthenticationError("authentication required")


class AnonymousResolver:
    def supports(self, credential: CredentialPresentation) -> bool:
        return credential.kind is CredentialKind.NONE

    def resolve(self, request: AuthRequest, credential: CredentialPresentation) -> RequestIdentity | None:
        if request.protection.allow_anonymous:
            return RequestIdentity.anonymous()
        return None


class SessionCredentialResolver:
    def __init__(self, sessions: SessionService, clock: Clock) -> None:
        self._sessions = sessions
        self._clock = clock

    def supports(self, credential: CredentialPresentation) -> bool:
        return credential.kind is CredentialKind.SESSION_ID

    def resolve(self, request: AuthRequest, credential: CredentialPresentation) -> RequestIdentity | None:
        if not credential.value_ref:
            return None
        session = self._sessions.get_session(SessionId(credential.value_ref))
        if session is None:
            return None
        return RequestIdentity(
            subject=SubjectRef.user(session.account_id),
            account_id=session.account_id,
            auth_method=AuthMethod.SESSION,
            authenticated_at=session.created_at,
            session_id=session.id,
        )


class AccessTokenCredentialResolver:
    def __init__(self, tokens: TokenService, clock: Clock) -> None:
        self._tokens = tokens
        self._clock = clock

    def supports(self, credential: CredentialPresentation) -> bool:
        return credential.kind is CredentialKind.ACCESS_TOKEN

    def resolve(self, request: AuthRequest, credential: CredentialPresentation) -> RequestIdentity | None:
        if not credential.value_ref:
            return None
        principal = self._tokens.verify_access_token(credential.value_ref)
        return RequestIdentity(
            subject=principal.subject,
            account_id=principal.account_id,
            auth_method=AuthMethod.ACCESS_TOKEN,
            authenticated_at=self._clock.now(),
            token_id=principal.jti,
        )


class LocalSecretResolver:
    def supports(self, credential: CredentialPresentation) -> bool:
        return credential.kind is CredentialKind.LOCAL_SECRET

    def resolve(self, request: AuthRequest, credential: CredentialPresentation) -> RequestIdentity | None:
        return None


class AssertedAccountResolver:
    def __init__(self, accounts: AccountRepository, clock: Clock) -> None:
        self._accounts = accounts
        self._clock = clock

    def supports(self, credential: CredentialPresentation) -> bool:
        return credential.kind is CredentialKind.ASSERTED_ACCOUNT

    def resolve(self, request: AuthRequest, credential: CredentialPresentation) -> RequestIdentity | None:
        if not request.origin.trusted:
            raise ValidationError("asserted account requires trusted origin")
        if not credential.value_ref:
            return None
        account = self._accounts.get_by_id(AccountId(credential.value_ref))
        if account is None or not account.is_active():
            return None
        return RequestIdentity(
            subject=SubjectRef.user(account.id),
            account_id=account.id,
            auth_method=AuthMethod.ASSERTED,
            authenticated_at=self._clock.now(),
        )
