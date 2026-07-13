# SPDX-License-Identifier: CC-BY-SA-4.0
"""OidcAuthClient — Authorization Code + PKCE per Keycloak e Authentik.

Supporta RS256, RS384, RS512, ES256, ES384, ES512.
La OIDC discovery viene cachata per 1 ora.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import ssl
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple
from urllib.parse import urlencode

import jwt
import requests
from jwt import PyJWKClient

from ...domain.exceptions import AuthenticationError

logger = logging.getLogger(__name__)

_OIDC_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]
_DISCOVERY_TTL = 3600.0


@dataclass
class OidcTokenSet:
    access_token: str
    id_token: str
    refresh_token: Optional[str] = None
    expires_in: int = 3600


class OidcAuthClient:
    """Client OIDC per Authorization Code + PKCE.

    Parametri di costruzione:
        issuer_url     URL emittente OIDC, es. https://auth.example.com/realms/myrealm
                       (Keycloak) o https://auth.example.com/application/o/myapp/
                       (Authentik).  Viene usato come base per /.well-known/openid-configuration.
        client_id      Client ID registrato sul provider.
        client_secret  Client secret per client confidenziali (opzionale per PKCE puro).
        scopes         Scopes richiesti (default: openid profile email).
    """

    def __init__(
        self,
        issuer_url: str,
        client_id: str,
        client_secret: Optional[str] = None,
        scopes: Optional[list] = None,
        verify: bool | str = True,
    ) -> None:
        self._issuer = issuer_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._scopes = scopes or ["openid", "profile", "email"]
        # Policy TLS verso l'IdP: True (default), False (solo sviluppo) oppure
        # path a un CA bundle custom (IdP con certificato self-signed). Propagata
        # a discovery, token endpoint e recupero JWKS.
        self._verify = verify
        self._discovery: Optional[dict] = None
        self._discovery_expires: float = 0.0
        self._jwks_client: Optional[PyJWKClient] = None

    # ------------------------------------------------------------------
    # Discovery (cachata)
    # ------------------------------------------------------------------

    def _jwks_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Contesto TLS per il recupero JWKS coerente con la policy ``verify``.

        None quando la verifica è quella di default (``verify is True``): in tal
        caso PyJWKClient usa il contesto di sistema.
        """
        if self._verify is True:
            return None
        if self._verify is False:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        # CA bundle custom (path).
        return ssl.create_default_context(cafile=self._verify)

    def _get_discovery(self) -> dict:
        if self._discovery and time.monotonic() < self._discovery_expires:
            return self._discovery
        url = f"{self._issuer}/.well-known/openid-configuration"
        try:
            resp = requests.get(url, timeout=10, verify=self._verify)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise AuthenticationError(f"OIDC discovery fallita: {exc}") from exc
        self._discovery = resp.json()
        self._discovery_expires = time.monotonic() + _DISCOVERY_TTL
        self._jwks_client = PyJWKClient(
            self._discovery["jwks_uri"],
            cache_keys=True,
            ssl_context=self._jwks_ssl_context(),
        )
        return self._discovery

    # ------------------------------------------------------------------
    # PKCE helpers
    # ------------------------------------------------------------------

    @staticmethod
    def generate_pkce_pair() -> Tuple[str, str]:
        """Restituisce (code_verifier, state) crittograficamente casuali."""
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        return verifier, state

    @staticmethod
    def _pkce_challenge(verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    # ------------------------------------------------------------------
    # Authorization URL
    # ------------------------------------------------------------------

    def build_auth_url(
        self,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_verifier: str,
        prompt: Optional[str] = None,
    ) -> str:
        disc = self._get_discovery()
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self._scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": self._pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
        if prompt:
            params["prompt"] = prompt
        return f"{disc['authorization_endpoint']}?{urlencode(params)}"

    def build_logout_url(
        self,
        post_logout_redirect_uri: str = "",
        id_token_hint: Optional[str] = None,
    ) -> Optional[str]:
        """Costruisce la RP-initiated logout URL dell'IdP, se esposta."""
        disc = self._get_discovery()
        endpoint = disc.get("end_session_endpoint")
        if not endpoint:
            return None
        params = {"client_id": self._client_id}
        if post_logout_redirect_uri:
            params["post_logout_redirect_uri"] = post_logout_redirect_uri
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        return f"{endpoint}?{urlencode(params)}"

    # ------------------------------------------------------------------
    # Token exchange
    # ------------------------------------------------------------------

    def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> OidcTokenSet:
        disc = self._get_discovery()
        data: dict = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._client_id,
            "code_verifier": code_verifier,
        }
        if self._client_secret:
            data["client_secret"] = self._client_secret
        try:
            resp = requests.post(
                disc["token_endpoint"], data=data, timeout=15, verify=self._verify
            )
        except requests.RequestException as exc:
            raise AuthenticationError(f"Token endpoint irraggiungibile: {exc}") from exc
        if not resp.ok:
            logger.warning(
                "OIDC token exchange fallito: HTTP %s — %s",
                resp.status_code,
                resp.text[:200],
            )
            raise AuthenticationError("OIDC token exchange fallito")
        body = resp.json()
        return OidcTokenSet(
            access_token=body.get("access_token", ""),
            id_token=body.get("id_token", ""),
            refresh_token=body.get("refresh_token"),
            expires_in=body.get("expires_in", 3600),
        )

    # ------------------------------------------------------------------
    # Token validation
    # ------------------------------------------------------------------

    def validate_id_token(self, id_token: str, nonce: str) -> dict:
        """Valida l'ID token e verifica il nonce (anti-replay).

        Supporta RS256/RS384/RS512/ES256/ES384/ES512.
        """
        disc = self._get_discovery()
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)
            kwargs: dict = {
                "algorithms": _OIDC_ALGORITHMS,
                "audience": self._client_id,
                "leeway": 30,  # tollera un minimo di clock-skew tra app e IdP
                "options": {"require": ["exp", "iat", "sub", "nonce"]},
            }
            # Difesa in profondità: verifica iss == issuer della discovery (P5).
            issuer = disc.get("issuer")
            if issuer:
                kwargs["issuer"] = issuer
                kwargs["options"]["require"].append("iss")
            payload = jwt.decode(id_token, signing_key.key, **kwargs)
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("ID token OIDC scaduto") from None
        except jwt.InvalidTokenError as exc:
            logger.debug("ID token non valido: %s", exc)
            raise AuthenticationError("ID token OIDC non valido") from None

        if payload.get("nonce") != nonce:
            raise AuthenticationError("Nonce non corrispondente: possibile replay attack")
        return payload

    def validate_access_token(
        self,
        access_token: str,
        issuer: Optional[str] = None,
        audience: Optional[str] = None,
    ) -> dict:
        """Valida un access token OIDC (per autenticazione REST Bearer).

        Supporta RS256/RS384/RS512/ES256/ES384/ES512.
        """
        if not self._jwks_client:
            self._get_discovery()
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(access_token)
            kwargs: dict = {
                "algorithms": _OIDC_ALGORITHMS,
                "leeway": 30,  # tollera un minimo di clock-skew tra app e IdP
                "options": {"require": ["exp", "iat", "sub"]},
            }
            if issuer:
                kwargs["issuer"] = issuer
            if audience:
                kwargs["audience"] = audience
            payload = jwt.decode(access_token, signing_key.key, **kwargs)
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Access token OIDC scaduto") from None
        except jwt.InvalidTokenError as exc:
            logger.debug("Access token non valido: %s", exc)
            raise AuthenticationError("Access token OIDC non valido") from None
        return payload

    def get_jwks_url(self) -> str:
        return self._get_discovery()["jwks_uri"]
