# SPDX-License-Identifier: CC-BY-SA-4.0
"""OIDC ports and trusted claim mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from auth.domain.identity import OidcClaims, OidcTransaction
from auth.domain.profile import AuthorizationProfile
from auth.domain.types import ProfileId


class OidcProviderClient(Protocol):
    def authorization_url(self, state: str, nonce: str, pkce_verifier: str, intent: str) -> str: ...

    def exchange_code(self, code: str, pkce_verifier: str, nonce: str) -> OidcClaims: ...

    def logout_url(self, id_token_hint: str | None, post_logout_redirect_uri: str | None) -> str | None: ...


class OidcTransactionStore(Protocol):
    def save(self, tx: OidcTransaction) -> None: ...

    def consume(self, provider: str, state: str) -> OidcTransaction | None: ...


@dataclass(frozen=True)
class TrustedClaimMappingPolicy:
    enabled: bool = False
    issuer_allowlist: frozenset[str] = frozenset()
    audience_allowlist: frozenset[str] = frozenset()
    level_claim: str = "acl_level"
    groups_claim: str = "groups"
    profile_id: ProfileId | None = None

    def map_claims(self, claims: OidcClaims) -> AuthorizationProfile:
        if not self.enabled:
            return AuthorizationProfile.anonymous()
        if self.issuer_allowlist and claims.issuer not in self.issuer_allowlist:
            return AuthorizationProfile.anonymous()
        if self.audience_allowlist and claims.audience not in self.audience_allowlist:
            return AuthorizationProfile.anonymous()
        level = self._level_from(claims.extra_claims)
        groups = self._groups_from(claims.extra_claims)
        return AuthorizationProfile(
            id=self.profile_id,
            level=level,
            groups=frozenset(groups),
            version=0,
        )

    def _level_from(self, extra_claims: Mapping[str, object]) -> int:
        value = extra_claims.get(self.level_claim, AuthorizationProfile.anonymous().level)
        if isinstance(value, bool):
            return AuthorizationProfile.anonymous().level
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return AuthorizationProfile.anonymous().level

    def _groups_from(self, extra_claims: Mapping[str, object]) -> set[str]:
        value = extra_claims.get(self.groups_claim, ())
        if isinstance(value, str):
            return {value}
        if isinstance(value, (list, tuple, set, frozenset)):
            return {item for item in value if isinstance(item, str)}
        return set()
