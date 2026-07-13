# SPDX-License-Identifier: CC-BY-SA-4.0
"""OIDC federation service."""

from __future__ import annotations

import hmac
from datetime import timedelta

from auth.application.dtos import AuthContext, OidcIntent, OidcStartResult, OidcAccountResolution
from auth.domain.account import Account, AccountKind, AccountStatus
from auth.domain.errors import AuthenticationError, ValidationError
from auth.domain.identity import ExternalIdentity, OidcClaims, OidcTransaction
from auth.domain.profile import AuthorizationProfile
from auth.domain.types import AccountId, ExternalIdentityId, ProfileId
from auth.ports.audit import AuditLogger
from auth.ports.oidc import OidcProviderClient, OidcTransactionStore, TrustedClaimMappingPolicy
from auth.ports.repositories import (
    AccountManagementRepository,
    CredentialRepository,
    ExternalIdentityRepository,
    ProfileRepository,
)
from auth.ports.security import Clock, SecureRandom


class OidcService:
    def __init__(
        self,
        providers: dict[str, OidcProviderClient],
        transactions: OidcTransactionStore,
        accounts: AccountManagementRepository,
        external_identities: ExternalIdentityRepository,
        credentials: CredentialRepository,
        clock: Clock,
        random: SecureRandom,
        *,
        profiles: ProfileRepository | None = None,
        claim_mapping: TrustedClaimMappingPolicy | None = None,
        auto_provision: bool = False,
        transaction_ttl: timedelta = timedelta(minutes=5),
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._providers = providers
        self._transactions = transactions
        self._accounts = accounts
        self._external_identities = external_identities
        self._credentials = credentials
        self._clock = clock
        self._random = random
        self._profiles = profiles
        self._claim_mapping = claim_mapping or TrustedClaimMappingPolicy()
        self._auto_provision = auto_provision
        self._transaction_ttl = transaction_ttl
        self._audit = audit_logger

    def begin(self, provider: str, intent: OidcIntent, context: AuthContext) -> OidcStartResult:
        client = self._provider(provider)
        now = self._clock.now()
        tx = OidcTransaction(
            provider=provider,
            state=self._random.token_urlsafe(32),
            nonce=self._random.token_urlsafe(32),
            pkce_verifier=self._random.token_urlsafe(48),
            intent=intent.value,
            created_at=now,
            expires_at=now + self._transaction_ttl,
            return_target=context.return_target,
            origin_ref=context.origin,
        )
        self._transactions.save(tx)
        self._audit_event("OIDC_BEGIN", provider=provider, intent=intent.value)
        return OidcStartResult(
            authorization_url=client.authorization_url(tx.state, tx.nonce, tx.pkce_verifier, intent.value),
            state=tx.state,
            expires_at=tx.expires_at,
        )

    def complete(self, provider: str, code: str, state: str, context: AuthContext) -> OidcAccountResolution:
        client = self._provider(provider)
        tx = self._transactions.consume(provider, state)
        if tx is None or tx.expires_at <= self._clock.now() or not hmac.compare_digest(tx.state, state):
            self._audit_event("OIDC_CALLBACK_DENIED", provider=provider, reason="state")
            raise AuthenticationError("authentication failed")
        claims = client.exchange_code(code, tx.pkce_verifier, tx.nonce)
        if not hmac.compare_digest(claims.nonce, tx.nonce) or claims.expires_at <= self._clock.now():
            self._audit_event("OIDC_CALLBACK_DENIED", provider=provider, reason="claims")
            raise AuthenticationError("authentication failed")
        external = self._external_identities.get_by_provider_issuer_subject(provider, claims.issuer, claims.subject)
        if external is None:
            if not self._auto_provision and tx.intent != OidcIntent.FIRST_ADMIN.value:
                self._audit_event("OIDC_CALLBACK_DENIED", provider=provider, reason="not_provisioned")
                raise AuthenticationError("authentication failed")
            external = self._provision(provider, claims)
        account = self._accounts.get_by_id(external.account_id)
        if account is None or not account.is_active() or self._credentials.get(account.id) is not None:
            self._audit_event("OIDC_CALLBACK_DENIED", provider=provider, reason="mixed_or_inactive")
            raise AuthenticationError("authentication failed")
        return OidcAccountResolution(
            account_id=account.id,
            identity_provider_id=str(external.id),
            profile_was_mapped=self._claim_mapping.enabled,
        )

    def migrate_identity(self, account_id: AccountId, claims: OidcClaims, context: AuthContext) -> ExternalIdentity:
        if self._credentials.get(account_id) is not None:
            raise ValidationError("cannot attach OIDC identity to an account with local credentials")
        external = ExternalIdentity(
            id=ExternalIdentityId(self._random.uuid4_hex()),
            account_id=account_id,
            provider=context.origin,
            issuer=claims.issuer,
            subject=claims.subject,
            email=claims.email,
            display_name=claims.display_name,
            linked_at=self._clock.now(),
        )
        self._external_identities.save(external)
        return external

    def remove_identity_for_migration(self, account_id: AccountId, external_identity_id: ExternalIdentityId) -> None:
        identities = self._external_identities.list_for_account(account_id)
        if len(identities) <= 1:
            raise ValidationError("cannot remove the last OIDC identity without an explicit replacement")
        self._external_identities.delete(external_identity_id)

    def _provider(self, provider: str) -> OidcProviderClient:
        try:
            return self._providers[provider]
        except KeyError as exc:
            raise ValidationError(f"unknown OIDC provider: {provider}") from exc

    def _provision(self, provider: str, claims: OidcClaims) -> ExternalIdentity:
        now = self._clock.now()
        mapped_profile = self._claim_mapping.map_claims(claims)
        profile_id = mapped_profile.id or ProfileId(f"oidc:{provider}:default")
        if self._profiles is not None and self._profiles.get(profile_id) is None:
            self._profiles.save(AuthorizationProfile(profile_id, mapped_profile.level, mapped_profile.groups, mapped_profile.version))
        account = Account(
            id=self._accounts.next_id(),
            username=claims.email.casefold() if claims.email else None,
            email=claims.email.casefold() if claims.email else None,
            kind=AccountKind.HUMAN,
            status=AccountStatus.ACTIVE,
            profile_id=profile_id,
            authz_version=0,
            flags=frozenset(),
            created_at=now,
            updated_at=now,
        )
        self._accounts.save(account)
        external = ExternalIdentity(
            id=ExternalIdentityId(self._random.uuid4_hex()),
            account_id=account.id,
            provider=provider,
            issuer=claims.issuer,
            subject=claims.subject,
            email=claims.email,
            display_name=claims.display_name,
            linked_at=now,
        )
        self._external_identities.save(external)
        return external

    def _audit_event(self, event_type: str, **fields: object) -> None:
        if self._audit is not None:
            self._audit.record(event_type, **fields)
