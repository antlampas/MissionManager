# SPDX-License-Identifier: CC-BY-SA-4.0
"""Static OIDC client useful for tests and contract development."""

from __future__ import annotations

from auth.domain.errors import AuthenticationError
from auth.domain.identity import OidcClaims


class StaticOidcProviderClient:
    def __init__(self, authorization_base_url: str, claims_by_code: dict[str, OidcClaims] | None = None) -> None:
        self._authorization_base_url = authorization_base_url
        self._claims_by_code = claims_by_code or {}

    def authorization_url(self, state: str, nonce: str, pkce_verifier: str, intent: str) -> str:
        return f"{self._authorization_base_url}?state={state}&nonce={nonce}&intent={intent}"

    def exchange_code(self, code: str, pkce_verifier: str, nonce: str) -> OidcClaims:
        claims = self._claims_by_code.get(code)
        if claims is None:
            raise AuthenticationError("authentication failed")
        return claims

    def logout_url(self, id_token_hint: str | None, post_logout_redirect_uri: str | None) -> str | None:
        return post_logout_redirect_uri
