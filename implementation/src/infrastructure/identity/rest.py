# SPDX-License-Identifier: CC-BY-SA-4.0
"""RestOperatorIdentityAdapter — valida Bearer token (locale o OIDC) e risolve Person.

Logica di dispatch:
  1. Estrae il Bearer token dall'header Authorization.
  2. Decodifica (senza verifica firma) il claim 'iss'.
  3. Se iss == 'missionmanager' e local_auth è configurato → verifica HS256 locale.
  4. Altrimenti, se jwks_url è configurato → verifica OIDC via JWKS (RS256/ES256…).
  5. In entrambi i casi, 'sub' deve essere un UUID valido che mappa a Person.id.

Eccezioni:
  AuthenticationError (→ 401) per token mancante/malformato/scaduto/revocato.
  AuthorizationError  (→ 403) viene sollevata dal middleware ACL, non qui.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

import jwt
from jwt import PyJWKClient
from quart import request

from ...infrastructure.auth.local import LocalAuthAdapter
from ...infrastructure.identity.base import OperatorIdentityAdapter
from ...domain.acl import Profile
from ...domain.entities import Person
from ...domain.exceptions import AuthenticationError, ValidationError
from ...domain.repositories import PersonRepository

logger = logging.getLogger(__name__)

_LOCAL_ISSUER = "missionmanager"
_OIDC_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]
# Claim del token che, se presenti, portano il profilo ACL ed evitano il
# round-trip all'admin API dell'IdP a ogni richiesta (P4).
_CLAIM_ACL_LEVEL = "acl_level"
_CLAIM_ACL_GROUPS = "acl_groups"


class RestOperatorIdentityAdapter(OperatorIdentityAdapter):

    def __init__(
        self,
        person_repo: PersonRepository,
        local_auth: Optional[LocalAuthAdapter] = None,
        jwks_url: Optional[str] = None,
        audience: Optional[str] = None,
        issuer: Optional[str] = None,
        dev_mode: bool = False,
        uow=None,
    ) -> None:
        super().__init__(person_repo, uow=uow)
        self._local_auth = local_auth
        self._jwks_client = PyJWKClient(jwks_url, cache_keys=True) if jwks_url else None
        self._audience = audience
        self._issuer = issuer
        self._dev_mode = dev_mode

    def get_current_operator(self) -> Person:
        token = self._extract_bearer()

        if not token:
            if self._dev_mode and not self._jwks_client and not self._local_auth:
                return self._dev_mode_fallback()
            raise AuthenticationError("Bearer token mancante")

        person_id, operator = self._dispatch(token)
        # Se il token porta l'ACL nei claim, l'operatore è già materializzato:
        # niente round-trip all'admin API dell'IdP (P4).
        return operator if operator is not None else self._get_person(person_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _dispatch(self, token: str) -> tuple[UUID, Optional[Person]]:
        """Restituisce (person_id, operatore-dai-claim-o-None).

        Il secondo elemento è valorizzato solo per i token OIDC che includono
        l'ACL nei claim; altrimenti l'operatore va materializzato dal repository.
        """
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.InvalidTokenError:
            raise AuthenticationError("Token JWT malformato") from None

        iss = unverified.get("iss", "")

        if iss == _LOCAL_ISSUER and self._local_auth:
            return self._local_auth.verify_token(token), None

        if self._jwks_client:
            return self._validate_oidc(token)

        raise AuthenticationError(
            "Nessun metodo di autenticazione disponibile per il token presentato"
        )

    def _validate_oidc(self, token: str) -> tuple[UUID, Optional[Person]]:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            kwargs: dict = {
                "algorithms": _OIDC_ALGORITHMS,
                "options": {"require": ["exp", "iat", "sub"]},
            }
            if self._audience:
                kwargs["audience"] = self._audience
            if self._issuer:
                kwargs["issuer"] = self._issuer
            payload = jwt.decode(token, signing_key.key, **kwargs)
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token OIDC scaduto") from None
        except jwt.InvalidTokenError as exc:
            logger.debug("Token OIDC non valido: %s", exc)
            raise AuthenticationError("Token OIDC non valido") from None

        sub = payload.get("sub", "")
        resolver = getattr(self._person_repo, "resolve_external_subject", None)
        if callable(resolver):
            person_id = resolver(str(sub))
        else:
            try:
                person_id = UUID(sub)
            except ValueError:
                raise AuthenticationError(
                    f"Claim 'sub' non è un UUID valido: {sub!r}"
                ) from None

        acl = self._acl_from_claims(payload)
        if acl is None:
            return person_id, None
        nickname = (
            payload.get("preferred_username")
            or payload.get("name")
            or str(sub)
        )
        return person_id, Person(id=person_id, nicknames=[nickname], acl=acl)

    @staticmethod
    def _acl_from_claims(payload: dict) -> Optional[Profile]:
        """Profilo dai claim del token, se presenti; None per il fallback all'admin API."""
        level = payload.get(_CLAIM_ACL_LEVEL)
        groups = payload.get(_CLAIM_ACL_GROUPS)
        if level is None:
            return None
        if isinstance(groups, str):
            groups = [g.strip() for g in groups.split(",") if g.strip()]
        try:
            return Profile(
                level=int(level),
                groups=frozenset(str(g) for g in (groups or [])),
            )
        except (ValueError, TypeError, ValidationError):
            logger.debug(
                "Claim ACL non interpretabili: acl_level=%r acl_groups=%r", level, groups
            )
            return None

    def _extract_bearer(self) -> Optional[str]:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:]
        return None

    def _dev_mode_fallback(self) -> Person:
        logger.warning(
            "dev_mode attivo: autenticazione via X-Operator-Id. NON usare in produzione."
        )
        raw = request.headers.get("X-Operator-Id")
        if not raw:
            raise AuthenticationError("dev_mode: X-Operator-Id header mancante")
        try:
            uid = UUID(raw)
        except ValueError:
            raise AuthenticationError("X-Operator-Id non è un UUID valido") from None
        return self._get_person(uid)
