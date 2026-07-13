# SPDX-License-Identifier: CC-BY-SA-4.0
"""Stdlib configuration DTOs for Auth bootstrap."""

from __future__ import annotations

from dataclasses import dataclass, field

from auth.domain.errors import ConfigurationError


@dataclass(frozen=True)
class AuthenticationSettings:
    mode: str


@dataclass(frozen=True)
class PasswordSettings:
    hasher: str = "argon2id"
    min_length: int = 12
    require_uppercase: bool = True
    require_digit: bool = True
    require_special: bool = True
    bcrypt_compat: bool = False


@dataclass(frozen=True)
class LocalSettings:
    max_failed_attempts: int = 5
    lockout_duration_seconds: int = 300


@dataclass(frozen=True)
class SessionSettings:
    backend: str = "memory"
    max_age_seconds: int = 28_800
    opaque_id_bytes: int = 32
    anti_forgery_enabled: bool = True


@dataclass(frozen=True)
class IngressSettings:
    require_secure_ambient_transport: bool = True
    reject_unmapped_mutations: bool = False


@dataclass(frozen=True)
class TokenSettings:
    issuer: str = "auth"
    audience: str = "consumer"
    access_ttl_seconds: int = 900
    refresh_enabled: bool = True
    refresh_ttl_seconds: int = 2_592_000
    revocation_backend: str = "memory"
    signing_secret: str = "dev-auth-secret-change-me"


@dataclass(frozen=True)
class OidcProviderSettings:
    name: str
    issuer: str
    client_id: str
    redirect_uri: str
    scopes: tuple[str, ...] = ("openid", "profile", "email")
    pkce: bool = True
    auto_provision: bool = False
    trusted_claim_mapping: bool = False
    verify_tls: bool = True


@dataclass(frozen=True)
class OidcSettings:
    transaction_ttl_seconds: int = 300
    allow_first_oidc_admin: bool = False
    providers: tuple[OidcProviderSettings, ...] = ()


@dataclass(frozen=True)
class AccessControlExtensionSettings:
    id: str
    package: str | None = None
    settings: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AccessControlSettings:
    model: str
    fail_on_missing_capability: bool = True
    extensions: tuple[AccessControlExtensionSettings, ...] = ()


@dataclass(frozen=True)
class AuthSettings:
    authentication: AuthenticationSettings
    access_control: AccessControlSettings
    password: PasswordSettings = field(default_factory=PasswordSettings)
    local: LocalSettings = field(default_factory=LocalSettings)
    session: SessionSettings = field(default_factory=SessionSettings)
    ingress: IngressSettings = field(default_factory=IngressSettings)
    token: TokenSettings = field(default_factory=TokenSettings)
    oidc: OidcSettings = field(default_factory=OidcSettings)
    environment: str = "development"

    def validate(self) -> None:
        mode = self.authentication.mode
        if mode not in {"local", "oidc"}:
            raise ConfigurationError("authentication.mode must be local or oidc")
        if not self.access_control.model:
            raise ConfigurationError("access_control.model is required")
        if mode == "local":
            if self.oidc.providers or self.oidc.allow_first_oidc_admin:
                raise ConfigurationError("OIDC providers and first-admin OIDC are invalid in local mode")
        if mode == "oidc":
            if not self.oidc.providers:
                raise ConfigurationError("oidc.providers is required in oidc mode")
        if self.environment == "production":
            if self.token.revocation_backend == "memory":
                raise ConfigurationError("in-memory token revocation is not allowed in production")
            if self.session.backend == "memory":
                raise ConfigurationError("in-memory sessions are not allowed in production")
            if self.token.signing_secret == "dev-auth-secret-change-me":
                raise ConfigurationError("default token signing secret is not allowed in production")
            for provider in self.oidc.providers:
                if not provider.verify_tls:
                    raise ConfigurationError("verify_tls=false is not allowed in production")
        for provider in self.oidc.providers:
            if not provider.name or not provider.issuer or not provider.client_id:
                raise ConfigurationError("OIDC providers require name, issuer and client_id")

    @classmethod
    def local_dev(cls, *, access_control_model: str, password_hasher: str = "pbkdf2") -> AuthSettings:
        return cls(
            authentication=AuthenticationSettings("local"),
            access_control=AccessControlSettings(access_control_model),
            password=PasswordSettings(hasher=password_hasher),
        )
