# SPDX-License-Identifier: CC-BY-SA-4.0
"""Administrative account use cases."""

from __future__ import annotations

from datetime import datetime

from auth.application.authorization_service import AuthorizationService
from auth.application.session_service import SessionService
from auth.domain.account import Account, AccountFlag, AccountKind, AccountStatus
from auth.domain.access_control import SYSTEM_RESOURCE
from auth.domain.credentials import LocalCredential
from auth.domain.errors import AuthorizationDenied, ValidationError
from auth.domain.identity import RequestIdentity
from auth.domain.policies import PasswordPolicy
from auth.domain.types import AccountId, ProfileId
from auth.ports.audit import AuditLogger
from auth.ports.repositories import AccountManagementRepository, CredentialRepository, ProfileRepository
from auth.ports.security import Clock, PasswordHasher


class AccountService:
    def __init__(
        self,
        authentication_mode: str,
        accounts: AccountManagementRepository,
        credentials: CredentialRepository,
        profiles: ProfileRepository,
        authorization: AuthorizationService,
        clock: Clock,
        password_hasher: PasswordHasher,
        *,
        password_policy: PasswordPolicy | None = None,
        sessions: SessionService | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._mode = authentication_mode
        self._accounts = accounts
        self._credentials = credentials
        self._profiles = profiles
        self._authorization = authorization
        self._clock = clock
        self._hasher = password_hasher
        self._password_policy = password_policy or PasswordPolicy()
        self._sessions = sessions
        self._audit = audit_logger

    def create_account(
        self,
        actor: RequestIdentity,
        *,
        username: str | None,
        email: str | None,
        profile_id: ProfileId,
        password: str | None = None,
        kind: AccountKind = AccountKind.HUMAN,
        flags: frozenset[AccountFlag] = frozenset(),
    ) -> Account:
        self._authorization.require(actor, "MANAGE_ACCOUNTS", SYSTEM_RESOURCE)
        if self._profiles.get(profile_id) is None:
            raise ValidationError("profile does not exist")
        now = self._clock.now()
        account = Account(
            id=self._accounts.next_id(),
            username=username.strip().casefold() if username else None,
            email=email.strip().casefold() if email else None,
            kind=kind,
            status=AccountStatus.ACTIVE,
            profile_id=profile_id,
            authz_version=0,
            flags=frozenset(flags),
            created_at=now,
            updated_at=now,
        )
        self._accounts.save(account)
        if password is not None:
            if self._mode != "local":
                raise ValidationError("local credentials are only allowed in authentication.mode=local")
            self._password_policy.validate(password)
            self._credentials.save(self._credential_for(account.id, password, now, must_change=False))
        self._audit_event("ACCOUNT_CREATED", account_id=str(account.id))
        return account

    def disable_account(self, actor: RequestIdentity, account_id: AccountId) -> None:
        self._authorization.require(actor, "MANAGE_ACCOUNTS", SYSTEM_RESOURCE)
        if actor.account_id == account_id:
            raise AuthorizationDenied("self-disable is not allowed")
        account = self._require_account(account_id)
        self._accounts.save(account.mark_disabled(self._clock.now()))
        if self._sessions is not None:
            self._sessions.revoke_all_sessions(account_id)
        self._audit_event("ACCOUNT_DISABLED", account_id=str(account_id))

    def delete_account(self, actor: RequestIdentity, account_id: AccountId) -> None:
        self._authorization.require(actor, "MANAGE_ACCOUNTS", SYSTEM_RESOURCE)
        if actor.account_id == account_id:
            raise AuthorizationDenied("self-delete is not allowed")
        account = self._require_account(account_id)
        self._accounts.save(account.mark_deleted(self._clock.now()))
        if self._sessions is not None:
            self._sessions.revoke_all_sessions(account_id)
        self._audit_event("ACCOUNT_DELETED", account_id=str(account_id))

    def set_profile(self, actor: RequestIdentity, account_id: AccountId, profile_id: ProfileId) -> None:
        self._authorization.require(actor, "MANAGE_PROFILES", SYSTEM_RESOURCE)
        if actor.account_id == account_id:
            raise AuthorizationDenied("self-escalation is not allowed")
        if self._profiles.get(profile_id) is None:
            raise ValidationError("profile does not exist")
        account = self._require_account(account_id)
        self._accounts.save(account.with_profile(profile_id, self._clock.now()))
        self._audit_event("PROFILE_CHANGED", account_id=str(account_id), profile_id=str(profile_id))

    def set_password(self, actor: RequestIdentity, account_id: AccountId, password: str, *, must_change: bool = True) -> None:
        self._authorization.require(actor, "MANAGE_CREDENTIALS", SYSTEM_RESOURCE)
        if self._mode != "local":
            raise ValidationError("local credentials are only allowed in authentication.mode=local")
        self._password_policy.validate(password)
        self._require_account(account_id)
        self._credentials.save(self._credential_for(account_id, password, self._clock.now(), must_change=must_change))
        if self._sessions is not None:
            self._sessions.revoke_all_sessions(account_id)

    def _require_account(self, account_id: AccountId) -> Account:
        account = self._accounts.get_by_id(account_id)
        if account is None:
            raise ValidationError("account does not exist")
        return account

    def _credential_for(self, account_id: AccountId, password: str, now: datetime, *, must_change: bool) -> LocalCredential:
        return LocalCredential(
            account_id=account_id,
            password_hash=self._hasher.hash(password),
            hash_algorithm=self._hasher.algorithm,
            hash_version=self._hasher.version,
            failed_attempts=0,
            locked_until=None,
            password_changed_at=now,
            must_change=must_change,
        )

    def _audit_event(self, event_type: str, **fields: object) -> None:
        if self._audit is not None:
            self._audit.record(event_type, **fields)
