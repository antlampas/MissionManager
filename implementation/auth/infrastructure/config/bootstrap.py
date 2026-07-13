# SPDX-License-Identifier: CC-BY-SA-4.0
"""Default composition root for a local Auth runtime."""

from __future__ import annotations

from datetime import timedelta
from typing import Mapping

from auth.adapters.ingress.resolvers import (
    AccessTokenCredentialResolver,
    AnonymousResolver,
    AssertedAccountResolver,
    CompositeIdentityResolver,
    SessionCredentialResolver,
)
from auth.application.access_control_admin_service import (
    AccessControlAdministrationService,
    AccessControlExtensionAdminService,
)
from auth.application.access_control_registry import DefaultAccessControlModelRegistry
from auth.application.account_service import AccountService
from auth.application.authentication_service import AuthenticationService
from auth.application.authorization_service import AuthorizationService
from auth.application.bootstrap_service import BootstrapService, BootstrappedAuth
from auth.application.operation_catalog import StaticOperationCatalog
from auth.application.profile_provider import RepositoryProfileProvider
from auth.application.request_gateway import RequestGateway
from auth.application.session_service import SessionService
from auth.application.token_service import TokenService
from auth.domain.access_control import AccessControlModelExtension
from auth.domain.policies import PasswordPolicy
from auth.infrastructure.config.settings import AuthSettings
from auth.infrastructure.memory.repositories import InMemoryAuthRepository
from auth.infrastructure.security.audit import RepositoryAuditLogger
from auth.infrastructure.security.clock import SystemClock
from auth.infrastructure.security.password import Argon2idPasswordHasher, BcryptPasswordHasher, Pbkdf2PasswordHasher
from auth.infrastructure.security.protections import HmacAntiForgeryProtector, ReturnTargetRedirectValidator
from auth.infrastructure.security.random import SecretsSecureRandom
from auth.infrastructure.security.rate_limit import NoopRateLimitPolicy
from auth.infrastructure.security.token import HmacTokenSigner
from auth.ports.oidc import OidcProviderClient


def bootstrap_auth(
    settings: AuthSettings,
    *,
    access_control_models: list[AccessControlModelExtension],
    access_control_admins: Mapping[str, AccessControlExtensionAdminService] | None = None,
    repository: InMemoryAuthRepository | None = None,
    oidc_clients: Mapping[str, OidcProviderClient] | None = None,
) -> BootstrappedAuth:
    settings.validate()
    repo = repository or InMemoryAuthRepository()
    clock = SystemClock()
    random = SecretsSecureRandom()
    audit = RepositoryAuditLogger(repo)
    password_policy = PasswordPolicy(
        min_length=settings.password.min_length,
        require_uppercase=settings.password.require_uppercase,
        require_digit=settings.password.require_digit,
        require_special=settings.password.require_special,
    )
    hasher = _password_hasher(settings.password.hasher)
    sessions = SessionService(
        repo,
        repo,
        clock,
        random,
        max_age=timedelta(seconds=settings.session.max_age_seconds),
        opaque_id_bytes=settings.session.opaque_id_bytes,
    )
    signer = HmacTokenSigner(settings.token.signing_secret)
    tokens = TokenService(
        repo,
        repo,
        repo,
        signer,
        clock,
        random,
        issuer=settings.token.issuer,
        audience=settings.token.audience,
        access_ttl=timedelta(seconds=settings.token.access_ttl_seconds),
        refresh_ttl=timedelta(seconds=settings.token.refresh_ttl_seconds),
    )
    operation_catalog = StaticOperationCatalog.with_defaults()
    profile_provider = RepositoryProfileProvider(repo, repo, repo)
    registry = DefaultAccessControlModelRegistry(
        settings.access_control.model,
        access_control_models,
        providers={"operation_catalog": operation_catalog},
        settings={extension.id: extension.settings for extension in settings.access_control.extensions},
    )
    authorization = AuthorizationService(registry, profile_provider, operation_catalog, audit_logger=audit)
    access_admin = AccessControlAdministrationService(registry, access_control_admins)
    account_service = AccountService(
        settings.authentication.mode,
        repo,
        repo,
        repo,
        authorization,
        clock,
        hasher,
        password_policy=password_policy,
        sessions=sessions,
        audit_logger=audit,
    )
    identity_resolver = CompositeIdentityResolver(
        [
            SessionCredentialResolver(sessions, clock),
            AccessTokenCredentialResolver(tokens, clock),
            AssertedAccountResolver(repo, clock),
            AnonymousResolver(),
        ]
    )
    gateway = RequestGateway(
        identity_resolver,
        authorization,
        accounts=repo,
        rate_limit_policy=NoopRateLimitPolicy(),
        anti_forgery=HmacAntiForgeryProtector(settings.token.signing_secret),
        redirect_validator=ReturnTargetRedirectValidator(),
    )
    bootstrap = BootstrapService(
        settings.authentication.mode,
        repo,
        repo,
        repo,
        hasher,
        password_policy,
        clock,
        access_admin,
    )
    authentication = AuthenticationService(
        settings.authentication.mode,
        repo,
        repo,
        hasher,
        clock,
        password_policy=password_policy,
        sessions=sessions,
        tokens=tokens,
        external_identities=repo,
        oidc_service=None,
        audit_logger=audit,
        max_failed_attempts=settings.local.max_failed_attempts,
        lockout_duration=timedelta(seconds=settings.local.lockout_duration_seconds),
    )
    return BootstrappedAuth(
        request_gateway=gateway,
        authentication_service=authentication,
        authorization_service=authorization,
        account_service=account_service,
        session_service=sessions,
        token_service=tokens,
        bootstrap_service=bootstrap,
        access_control_admin_service=access_admin,
    )


def _password_hasher(name: str):
    if name == "argon2id":
        return Argon2idPasswordHasher()
    if name == "bcrypt":
        return BcryptPasswordHasher()
    if name == "pbkdf2":
        return Pbkdf2PasswordHasher()
    raise ValueError(f"unknown password hasher: {name}")
