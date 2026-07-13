# SPDX-License-Identifier: CC-BY-SA-4.0
"""Opaque server-side session service."""

from __future__ import annotations

from datetime import timedelta

from auth.application.dtos import AuthContext
from auth.domain.errors import AuthenticationError, ValidationError
from auth.domain.identity import AuthMethod
from auth.domain.session import AuthSession
from auth.domain.types import AccountId, SessionId
from auth.ports.repositories import AccountRepository, SessionRepository
from auth.ports.security import Clock, SecureRandom


class SessionService:
    def __init__(
        self,
        accounts: AccountRepository,
        sessions: SessionRepository,
        clock: Clock,
        random: SecureRandom,
        *,
        max_age: timedelta = timedelta(hours=8),
        opaque_id_bytes: int = 32,
    ) -> None:
        self._accounts = accounts
        self._sessions = sessions
        self._clock = clock
        self._random = random
        self._max_age = max_age
        self._opaque_id_bytes = opaque_id_bytes

    def create_session(
        self,
        account_id: AccountId,
        auth_context: AuthContext,
        *,
        auth_method: AuthMethod = AuthMethod.LOCAL_PASSWORD,
    ) -> AuthSession:
        account = self._accounts.get_by_id(account_id)
        if account is None or not account.is_active():
            raise AuthenticationError("authentication failed")
        now = self._clock.now()
        session = AuthSession(
            id=SessionId(self._random.token_urlsafe(self._opaque_id_bytes)),
            account_id=account.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + self._max_age,
            revoked_at=None,
            auth_method=auth_method,
            authz_version=account.authz_version,
            anti_forgery_secret_id=self._random.token_urlsafe(16),
        )
        self._sessions.create(session)
        return session

    def rotate_session(self, old_session_id: SessionId, account_id: AccountId) -> AuthSession:
        self.revoke_session(old_session_id)
        return self.create_session(account_id, AuthContext(current_session_id=old_session_id))

    def get_session(self, session_id: SessionId) -> AuthSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        now = self._clock.now()
        if not session.is_valid(now):
            return None
        account = self._accounts.get_by_id(session.account_id)
        if account is None or not account.is_active():
            return None
        if account.authz_version != session.authz_version:
            return None
        touched = session.touch(now)
        self._sessions.save(touched)
        return touched

    def revoke_session(self, session_id: SessionId) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        self._sessions.save(session.revoke(self._clock.now()))

    def revoke_all_sessions(self, account_id: AccountId) -> None:
        if not account_id:
            raise ValidationError("account_id is required")
        self._sessions.delete_for_account(account_id)
