# SPDX-License-Identifier: CC-BY-SA-4.0
"""Explicit access and refresh token service."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from auth.application.dtos import AccessToken, AuthContext, RefreshToken, TokenPair
from auth.domain.access_control import SubjectRef
from auth.domain.account import Account
from auth.domain.errors import AuthenticationError, ValidationError
from auth.domain.identity import AuthMethod
from auth.domain.token import RefreshTokenRecord, TokenPrincipal
from auth.domain.types import ClientRef, RefreshTokenId, TokenFamilyId
from auth.domain.types import AccountId
from auth.ports.repositories import AccountRepository, TokenRepository, TokenRevocationStore
from auth.ports.security import Clock, SecureRandom, TokenSigner, TokenValidationContext, ttl_seconds


class TokenService:
    def __init__(
        self,
        accounts: AccountRepository,
        tokens: TokenRepository,
        revocations: TokenRevocationStore,
        signer: TokenSigner,
        clock: Clock,
        random: SecureRandom,
        *,
        issuer: str = "auth",
        audience: str = "consumer",
        algorithms: frozenset[str] = frozenset({"HS256"}),
        access_ttl: timedelta = timedelta(minutes=15),
        refresh_ttl: timedelta = timedelta(days=30),
        refresh_token_bytes: int = 32,
    ) -> None:
        self._accounts = accounts
        self._tokens = tokens
        self._revocations = revocations
        self._signer = signer
        self._clock = clock
        self._random = random
        self._issuer = issuer
        self._audience = audience
        self._algorithms = algorithms
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl
        self._refresh_token_bytes = refresh_token_bytes

    def issue_access_token(self, account: Account, context: AuthContext) -> AccessToken:
        account.require_active()
        now = self._clock.now()
        expires_at = now + self._access_ttl
        jti = self._random.uuid4_hex()
        claims: dict[str, Any] = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(account.id),
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": jti,
            "authz_version": account.authz_version,
            "amr": AuthMethod.LOCAL_PASSWORD.value,
        }
        return AccessToken(value=self._signer.sign(claims), jti=jti, expires_at=expires_at)

    def verify_access_token(self, token: str) -> TokenPrincipal:
        now = self._clock.now()
        claims = self._signer.verify(
            token,
            TokenValidationContext(
                issuer=self._issuer,
                audience=self._audience,
                algorithms=self._algorithms,
                now=now,
            ),
        )
        jti = self._required_str(claims, "jti")
        if self._revocations.is_revoked(jti):
            raise AuthenticationError("authentication failed")
        account_id = AccountId(self._required_str(claims, "sub"))
        account = self._accounts.get_by_id(account_id)
        if account is None or not account.is_active():
            raise AuthenticationError("authentication failed")
        authz_version = int(claims.get("authz_version", -1))
        if account.authz_version != authz_version:
            raise AuthenticationError("authentication failed")
        expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)
        return TokenPrincipal(
            account_id=account.id,
            subject=SubjectRef.user(account.id),
            jti=jti,
            issuer=self._issuer,
            audience=self._audience,
            expires_at=expires_at,
            authz_version=authz_version,
            auth_method=AuthMethod.ACCESS_TOKEN,
        )

    def revoke_access_token(self, token: str) -> None:
        now = self._clock.now()
        claims = self._signer.verify(
            token,
            TokenValidationContext(self._issuer, self._audience, self._algorithms, now),
        )
        jti = self._required_str(claims, "jti")
        exp = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)
        self._revocations.revoke(jti, ttl_seconds(exp, now))

    def issue_refresh_token(self, account: Account, client: ClientRef | None = None) -> RefreshToken:
        account.require_active()
        now = self._clock.now()
        value = self._random.token_urlsafe(self._refresh_token_bytes)
        record = RefreshTokenRecord(
            id=RefreshTokenId(self._random.uuid4_hex()),
            family_id=TokenFamilyId(self._random.uuid4_hex()),
            account_id=account.id,
            token_hash=self._hash_token(value),
            issued_at=now,
            expires_at=now + self._refresh_ttl,
            rotated_at=None,
            revoked_at=None,
        )
        self._tokens.save_refresh_token(record)
        return RefreshToken(value=value, id=str(record.id), family_id=record.family_id, expires_at=record.expires_at)

    def rotate_refresh_token(self, refresh_token: str) -> TokenPair:
        now = self._clock.now()
        record = self._tokens.get_refresh_token_by_hash(self._hash_token(refresh_token))
        if record is None or not record.active(now):
            raise AuthenticationError("authentication failed")
        account = self._accounts.get_by_id(record.account_id)
        if account is None or not account.is_active():
            raise AuthenticationError("authentication failed")
        rotated = record.rotate(now)
        new_value = self._random.token_urlsafe(self._refresh_token_bytes)
        new_record = RefreshTokenRecord(
            id=RefreshTokenId(self._random.uuid4_hex()),
            family_id=record.family_id,
            account_id=record.account_id,
            token_hash=self._hash_token(new_value),
            issued_at=now,
            expires_at=now + self._refresh_ttl,
            rotated_at=None,
            revoked_at=None,
        )
        self._tokens.save_refresh_family([rotated, new_record])
        return TokenPair(
            access_token=self.issue_access_token(account, AuthContext(issue_session=False, issue_tokens=True)),
            refresh_token=RefreshToken(new_value, str(new_record.id), new_record.family_id, new_record.expires_at),
        )

    def revoke_refresh_family(self, family_id: TokenFamilyId) -> None:
        now = self._clock.now()
        records = [record.revoke(now) for record in self._tokens.list_refresh_family(family_id)]
        self._tokens.save_refresh_family(records)

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _required_str(self, claims: Mapping[str, Any], name: str) -> str:
        value = claims.get(name)
        if not isinstance(value, str) or not value:
            raise ValidationError(f"token missing claim {name}")
        return value
