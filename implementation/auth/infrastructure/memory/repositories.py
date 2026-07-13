# SPDX-License-Identifier: CC-BY-SA-4.0
"""In-memory repositories for tests and local development."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from auth.domain.account import Account
from auth.domain.credentials import LocalCredential
from auth.domain.identity import ExternalIdentity, OidcTransaction
from auth.domain.profile import AuthorizationProfile, Group
from auth.domain.session import AuthSession
from auth.domain.token import RefreshTokenRecord
from auth.domain.types import (
    AccountId,
    ExternalIdentityId,
    GroupId,
    ProfileId,
    RefreshTokenId,
    SessionId,
    TokenFamilyId,
)
from auth.ports.audit import AuditEvent


class InMemoryAuthRepository:
    def __init__(self) -> None:
        self.accounts: dict[AccountId, Account] = {}
        self.credentials: dict[AccountId, LocalCredential] = {}
        self.external_identities: dict[ExternalIdentityId, ExternalIdentity] = {}
        self.profiles: dict[ProfileId, AuthorizationProfile] = {}
        self.groups: dict[GroupId, Group] = {}
        self.memberships: dict[AccountId, set[str]] = {}
        self.sessions: dict[SessionId, AuthSession] = {}
        self.refresh_tokens: dict[RefreshTokenId, RefreshTokenRecord] = {}
        self.revoked_jti: dict[str, datetime] = {}
        self.oidc_transactions: dict[tuple[str, str], OidcTransaction] = {}
        self.audit_events: list[AuditEvent] = []

    def get_by_id(self, account_id: AccountId) -> Account | None:
        return self.accounts.get(account_id)

    def get_by_username(self, username: str) -> Account | None:
        normalized = username.strip().casefold()
        for account in self.accounts.values():
            if account.username and account.username.casefold() == normalized:
                return account
        return None

    def get_by_email(self, email: str) -> Account | None:
        normalized = email.strip().casefold()
        for account in self.accounts.values():
            if account.email and account.email.casefold() == normalized:
                return account
        return None

    def exists_active(self) -> bool:
        return any(account.is_active() for account in self.accounts.values())

    def save(self, item) -> None:
        if isinstance(item, Account):
            self.accounts[item.id] = item
        elif isinstance(item, LocalCredential):
            self.credentials[item.account_id] = item
        elif isinstance(item, ExternalIdentity):
            self.external_identities[item.id] = item
        elif isinstance(item, AuthorizationProfile):
            if item.id is None:
                raise ValueError("anonymous profile cannot be persisted")
            self.profiles[item.id] = item
        elif isinstance(item, Group):
            self.groups[item.id] = item
        elif isinstance(item, AuthSession):
            self.sessions[item.id] = item
        elif isinstance(item, OidcTransaction):
            self.oidc_transactions[(item.provider, item.state)] = item
        else:
            raise TypeError(f"unsupported item type: {type(item)!r}")

    def delete(self, item_id) -> None:
        self.accounts.pop(item_id, None)
        self.credentials.pop(item_id, None)
        self.external_identities.pop(item_id, None)
        self.profiles.pop(item_id, None)
        self.groups.pop(item_id, None)
        self.sessions.pop(item_id, None)

    def list(self):
        return list(self.accounts.values())

    def count(self) -> int:
        return len(self.accounts)

    def next_id(self) -> AccountId:
        return AccountId(uuid.uuid4().hex)

    def get(self, item_id):
        if item_id in self.credentials:
            return self.credentials[item_id]
        if item_id in self.profiles:
            return self.profiles[item_id]
        if item_id in self.groups:
            return self.groups[item_id]
        if item_id in self.sessions:
            return self.sessions[item_id]
        return None

    def record_failure(
        self,
        account_id: AccountId,
        *,
        now: datetime,
        max_attempts: int,
        lockout_duration: timedelta,
    ) -> LocalCredential | None:
        credential = self.credentials.get(account_id)
        if credential is None:
            return None
        next_attempts = credential.failed_attempts + 1
        locked_until = now + lockout_duration if next_attempts >= max_attempts else credential.locked_until
        updated = credential.with_failure(locked_until)
        self.credentials[account_id] = updated
        return updated

    def reset_failures(self, account_id: AccountId) -> LocalCredential | None:
        credential = self.credentials.get(account_id)
        if credential is None:
            return None
        updated = credential.reset_failures()
        self.credentials[account_id] = updated
        return updated

    def get_by_provider_issuer_subject(self, provider: str, issuer: str, subject: str) -> ExternalIdentity | None:
        for identity in self.external_identities.values():
            if identity.provider == provider and identity.issuer == issuer and identity.subject == subject:
                return identity
        return None

    def list_for_account(self, account_id: AccountId) -> list[ExternalIdentity]:
        return [identity for identity in self.external_identities.values() if identity.account_id == account_id]

    def assign_groups(self, profile_id: ProfileId, groups: frozenset[str]) -> AuthorizationProfile | None:
        profile = self.profiles.get(profile_id)
        if profile is None:
            return None
        updated = AuthorizationProfile(profile.id, profile.level, groups, profile.version + 1)
        self.profiles[profile_id] = updated
        return updated

    def increment_version(self, profile_id: ProfileId) -> AuthorizationProfile | None:
        profile = self.profiles.get(profile_id)
        if profile is None:
            return None
        updated = replace(profile, version=profile.version + 1)
        self.profiles[profile_id] = updated
        return updated

    def groups_for_account(self, account_id: AccountId) -> frozenset[str]:
        return frozenset(self.memberships.get(account_id, set()))

    def add(self, account_id: AccountId, group: str) -> None:
        self.memberships.setdefault(account_id, set()).add(group)

    def remove(self, account_id: AccountId, group: str) -> None:
        self.memberships.setdefault(account_id, set()).discard(group)

    def remove_all(self, account_id: AccountId) -> None:
        self.memberships.pop(account_id, None)

    def create(self, session: AuthSession) -> None:
        self.sessions[session.id] = session

    def delete_for_account(self, account_id: AccountId) -> None:
        for session_id, session in list(self.sessions.items()):
            if session.account_id == account_id:
                self.sessions.pop(session_id, None)

    def save_refresh_token(self, record: RefreshTokenRecord) -> None:
        self.refresh_tokens[record.id] = record

    def get_refresh_token_by_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        for record in self.refresh_tokens.values():
            if record.token_hash == token_hash:
                return record
        return None

    def get_refresh_token(self, token_id: RefreshTokenId) -> RefreshTokenRecord | None:
        return self.refresh_tokens.get(token_id)

    def list_refresh_family(self, family_id: TokenFamilyId) -> list[RefreshTokenRecord]:
        return [record for record in self.refresh_tokens.values() if record.family_id == family_id]

    def save_refresh_family(self, records: list[RefreshTokenRecord]) -> None:
        for record in records:
            self.refresh_tokens[record.id] = record

    def revoke(self, jti: str, ttl_seconds: int) -> None:
        self.revoked_jti[jti] = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

    def is_revoked(self, jti: str) -> bool:
        now = datetime.now(timezone.utc)
        expires_at = self.revoked_jti.get(jti)
        if expires_at is None:
            return False
        if expires_at <= now:
            self.revoked_jti.pop(jti, None)
            return False
        return True

    def append(self, event: AuditEvent) -> None:
        self.audit_events.append(event)

    def list_events(self) -> list[AuditEvent]:
        return list(self.audit_events)

    def save_transaction(self, tx: OidcTransaction) -> None:
        self.oidc_transactions[(tx.provider, tx.state)] = tx

    def consume(self, provider: str, state: str) -> OidcTransaction | None:
        return self.oidc_transactions.pop((provider, state), None)

    def entries_for(self, resource):
        return []

    def list_by_operation(self, operation: str):
        return []

    def delete_by_resource(self, resource) -> None:
        return None

    def delete_by_subject(self, subject) -> None:
        return None

    def policy_for(self, resource):
        return None

    def save_policy(self, policy: object) -> None:
        return None

    def delete_policy(self, policy_id: str) -> None:
        return None

    def grants_for(self, resource):
        return []

    def save_grant(self, grant: object) -> None:
        return None

    def delete_grant(self, grant_id: str) -> None:
        return None

    def controls_for(self, resource):
        return None

    def set_control(self, control: object) -> None:
        return None
