# SPDX-License-Identifier: CC-BY-SA-4.0
"""Bootstrap use cases and runtime container."""

from __future__ import annotations

from dataclasses import dataclass

from auth.application.access_control_admin_service import AccessControlAdministrationService
from auth.application.account_service import AccountService
from auth.application.authentication_service import AuthenticationService
from auth.application.authorization_service import AuthorizationService
from auth.application.request_gateway import RequestGateway
from auth.application.session_service import SessionService
from auth.application.token_service import TokenService
from auth.domain.account import Account, AccountFlag, AccountKind, AccountStatus
from auth.domain.credentials import LocalCredential
from auth.domain.errors import ValidationError
from auth.domain.identity import OidcClaims
from auth.domain.policies import PasswordPolicy
from auth.domain.profile import AuthorizationProfile
from auth.domain.types import AccountId, ProfileId
from auth.ports.repositories import AccountManagementRepository, CredentialRepository, ProfileRepository
from auth.ports.security import Clock, PasswordHasher


@dataclass(frozen=True)
class BootstrappedAuth:
    request_gateway: RequestGateway
    authentication_service: AuthenticationService
    authorization_service: AuthorizationService
    account_service: AccountService
    session_service: SessionService
    token_service: TokenService | None
    bootstrap_service: BootstrapService
    access_control_admin_service: AccessControlAdministrationService


class BootstrapService:
    def __init__(
        self,
        authentication_mode: str,
        accounts: AccountManagementRepository,
        credentials: CredentialRepository,
        profiles: ProfileRepository,
        password_hasher: PasswordHasher,
        password_policy: PasswordPolicy,
        clock: Clock,
        access_control_admin: AccessControlAdministrationService,
    ) -> None:
        self._mode = authentication_mode
        self._accounts = accounts
        self._credentials = credentials
        self._profiles = profiles
        self._hasher = password_hasher
        self._password_policy = password_policy
        self._clock = clock
        self._access_control_admin = access_control_admin

    def is_setup_required(self) -> bool:
        return self._accounts.count() == 0

    def create_initial_admin(self, username: str, password: str) -> AccountId:
        if self._mode != "local":
            raise ValidationError("local initial admin is only allowed in authentication.mode=local")
        if not self.is_setup_required():
            raise ValidationError("setup already completed")
        self._password_policy.validate(password)
        now = self._clock.now()
        profile_id = ProfileId("bootstrap-admin")
        self._profiles.save(AuthorizationProfile(profile_id, level=0, groups=frozenset({"admins"}), version=0))
        account = Account(
            id=self._accounts.next_id(),
            username=username.strip().casefold(),
            email=None,
            kind=AccountKind.HUMAN,
            status=AccountStatus.ACTIVE,
            profile_id=profile_id,
            authz_version=0,
            flags=frozenset({AccountFlag.BOOTSTRAP_SUPERUSER}),
            created_at=now,
            updated_at=now,
        )
        self._accounts.save(account)
        self._credentials.save(
            LocalCredential(
                account_id=account.id,
                password_hash=self._hasher.hash(password),
                hash_algorithm=self._hasher.algorithm,
                hash_version=self._hasher.version,
                failed_attempts=0,
                locked_until=None,
                password_changed_at=now,
                must_change=False,
            )
        )
        self.ensure_bootstrap_policies()
        return account.id

    def complete_first_oidc_admin(self, claims: OidcClaims) -> AccountId:
        raise ValidationError("first OIDC admin bootstrap requires an OIDC extension policy in the consumer runtime")

    def ensure_bootstrap_policies(self) -> None:
        self._access_control_admin.ensure_bootstrap_policies()
