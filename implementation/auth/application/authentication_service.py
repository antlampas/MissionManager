# SPDX-License-Identifier: CC-BY-SA-4.0
"""Authentication use cases."""

from __future__ import annotations

from datetime import timedelta

from auth.application.dtos import AuthContext, AuthenticationResult, LogoutResult, OidcIntent
from auth.application.oidc_service import OidcService
from auth.application.session_service import SessionService
from auth.application.token_service import TokenService
from auth.domain.access_control import SubjectRef
from auth.domain.account import AccountFlag
from auth.domain.errors import AuthenticationError, ValidationError
from auth.domain.identity import AuthMethod, RequestIdentity
from auth.domain.policies import PasswordPolicy
from auth.ports.audit import AuditLogger
from auth.ports.repositories import AccountRepository, CredentialRepository, ExternalIdentityRepository
from auth.ports.security import Clock, PasswordHasher


class AuthenticationService:
    def __init__(
        self,
        authentication_mode: str,
        accounts: AccountRepository,
        credentials: CredentialRepository,
        password_hasher: PasswordHasher,
        clock: Clock,
        *,
        password_policy: PasswordPolicy | None = None,
        sessions: SessionService | None = None,
        tokens: TokenService | None = None,
        external_identities: ExternalIdentityRepository | None = None,
        oidc_service: OidcService | None = None,
        audit_logger: AuditLogger | None = None,
        max_failed_attempts: int = 5,
        lockout_duration: timedelta = timedelta(minutes=5),
        dummy_password: str = "__auth_dummy_password__",
    ) -> None:
        self._mode = authentication_mode
        self._accounts = accounts
        self._credentials = credentials
        self._hasher = password_hasher
        self._clock = clock
        self._password_policy = password_policy or PasswordPolicy()
        self._sessions = sessions
        self._tokens = tokens
        self._external_identities = external_identities
        self._oidc_service = oidc_service
        self._audit = audit_logger
        self._max_failed_attempts = max_failed_attempts
        self._lockout_duration = lockout_duration
        self._dummy_hash = password_hasher.hash(dummy_password)

    def login_local(self, username: str, password: str, context: AuthContext | None = None) -> AuthenticationResult:
        self._require_mode("local")
        context = context or AuthContext()
        normalized = self._normalize_username(username)
        account = self._accounts.get_by_username(normalized)
        if account is None and "@" in normalized:
            account = self._accounts.get_by_email(normalized)
        if account is None:
            self._hasher.verify(password, self._dummy_hash)
            self._audit_event("LOCAL_LOGIN_DENIED", username=normalized, reason="generic")
            raise AuthenticationError("authentication failed")
        credential = self._credentials.get(account.id)
        if credential is None:
            self._hasher.verify(password, self._dummy_hash)
            self._audit_event("LOCAL_LOGIN_DENIED", account_id=str(account.id), reason="generic")
            raise AuthenticationError("authentication failed")
        if self._external_identities is not None and self._external_identities.list_for_account(account.id):
            self._audit_event("LOCAL_LOGIN_DENIED", account_id=str(account.id), reason="mixed_identity")
            raise AuthenticationError("authentication failed")
        now = self._clock.now()
        if not account.is_active() or credential.is_locked(now):
            self._audit_event("LOCAL_LOGIN_DENIED", account_id=str(account.id), reason="generic")
            raise AuthenticationError("authentication failed")
        if not self._hasher.verify(password, credential.password_hash):
            self._credentials.record_failure(
                account.id,
                now=now,
                max_attempts=self._max_failed_attempts,
                lockout_duration=self._lockout_duration,
            )
            self._audit_event("LOCAL_LOGIN_DENIED", account_id=str(account.id), reason="generic")
            raise AuthenticationError("authentication failed")
        credential = self._credentials.reset_failures(account.id) or credential
        if self._hasher.needs_rehash(credential.password_hash):
            credential = credential.with_password(self._hasher.hash(password), self._hasher.algorithm, self._hasher.version, now, must_change=credential.must_change)
            self._credentials.save(credential)
        must_change = credential.must_change or AccountFlag.MUST_CHANGE_PASSWORD in account.flags
        identity = RequestIdentity(
            subject=SubjectRef.user(account.id),
            account_id=account.id,
            auth_method=AuthMethod.LOCAL_PASSWORD,
            authenticated_at=now,
        )
        if must_change:
            self._audit_event("LOCAL_LOGIN_ALLOWED", account_id=str(account.id), must_change_password=True)
            return AuthenticationResult(account.id, identity, must_change_password=True, return_target=context.return_target)
        session = None
        access_token = None
        refresh_token = None
        if context.issue_session:
            if self._sessions is None:
                raise ValidationError("session service is not configured")
            session = self._sessions.create_session(account.id, context, auth_method=AuthMethod.LOCAL_PASSWORD)
            identity = RequestIdentity(
                subject=SubjectRef.user(account.id),
                account_id=account.id,
                auth_method=AuthMethod.SESSION,
                authenticated_at=now,
                session_id=session.id,
            )
        if context.issue_tokens:
            if self._tokens is None:
                raise ValidationError("token service is not configured")
            access_token = self._tokens.issue_access_token(account, context)
            if context.issue_refresh_token:
                refresh_token = self._tokens.issue_refresh_token(account, context.client_ref)
        self._audit_event("LOCAL_LOGIN_ALLOWED", account_id=str(account.id))
        return AuthenticationResult(
            account_id=account.id,
            identity=identity,
            session=session,
            access_token=access_token,
            refresh_token=refresh_token,
            return_target=context.return_target,
        )

    def begin_oidc(self, provider: str, intent: OidcIntent, context: AuthContext):
        self._require_mode("oidc")
        if self._oidc_service is None:
            raise ValidationError("OIDC service is not configured")
        return self._oidc_service.begin(provider, intent, context)

    def complete_oidc(self, provider: str, code: str, state: str, context: AuthContext | None = None) -> AuthenticationResult:
        self._require_mode("oidc")
        if self._oidc_service is None:
            raise ValidationError("OIDC service is not configured")
        context = context or AuthContext()
        resolution = self._oidc_service.complete(provider, code, state, context)
        account = self._accounts.get_by_id(resolution.account_id)
        if account is None or not account.is_active():
            raise AuthenticationError("authentication failed")
        now = self._clock.now()
        identity = RequestIdentity(SubjectRef.user(account.id), account.id, AuthMethod.OIDC, now)
        session = None
        access_token = None
        refresh_token = None
        if context.issue_session:
            if self._sessions is None:
                raise ValidationError("session service is not configured")
            session = self._sessions.create_session(account.id, context, auth_method=AuthMethod.OIDC)
            identity = RequestIdentity(SubjectRef.user(account.id), account.id, AuthMethod.SESSION, now, session_id=session.id)
        if context.issue_tokens:
            if self._tokens is None:
                raise ValidationError("token service is not configured")
            access_token = self._tokens.issue_access_token(account, context)
            if context.issue_refresh_token:
                refresh_token = self._tokens.issue_refresh_token(account, context.client_ref)
        self._audit_event("OIDC_CALLBACK_ALLOWED", account_id=str(account.id), provider=provider)
        return AuthenticationResult(
            account_id=account.id,
            identity=identity,
            session=session,
            access_token=access_token,
            refresh_token=refresh_token,
            return_target=context.return_target,
        )

    def logout(self, identity: RequestIdentity, context: AuthContext | None = None) -> LogoutResult:
        context = context or AuthContext()
        session_revoked = False
        if identity.session_id is not None and self._sessions is not None:
            self._sessions.revoke_session(identity.session_id)
            session_revoked = True
        self._audit_event("LOGOUT", account_id=str(identity.account_id) if identity.account_id else None)
        return LogoutResult(session_revoked=session_revoked, return_target=context.return_target)

    def change_password(self, identity: RequestIdentity, old_password: str, new_password: str) -> None:
        self._require_mode("local")
        if identity.account_id is None:
            raise AuthenticationError("authentication required")
        account = self._accounts.get_by_id(identity.account_id)
        credential = self._credentials.get(identity.account_id)
        if account is None or credential is None or not account.is_active():
            raise AuthenticationError("authentication failed")
        if self._external_identities is not None and self._external_identities.list_for_account(account.id):
            raise ValidationError("OIDC accounts cannot change a local password")
        if not self._hasher.verify(old_password, credential.password_hash):
            raise AuthenticationError("authentication failed")
        self._password_policy.validate(new_password)
        now = self._clock.now()
        self._credentials.save(
            credential.with_password(
                self._hasher.hash(new_password),
                self._hasher.algorithm,
                self._hasher.version,
                now,
            )
        )
        if self._sessions is not None:
            self._sessions.revoke_all_sessions(account.id)
        self._audit_event("PASSWORD_CHANGED", account_id=str(account.id))

    def _require_mode(self, expected: str) -> None:
        if self._mode != expected:
            raise ValidationError(f"authentication.mode must be {expected}")

    def _normalize_username(self, username: str) -> str:
        return username.strip().casefold()

    def _audit_event(self, event_type: str, **fields: object) -> None:
        if self._audit is not None:
            self._audit.record(event_type, **fields)
