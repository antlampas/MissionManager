# SPDX-License-Identifier: CC-BY-SA-4.0
"""AuthService — orchestrazione dei flussi di autenticazione locale e OIDC.

Due modalità:
  - local:  adapter MissionManager verso il package esterno ``auth``
            (bcrypt + token HMAC/JWT tramite LocalAuthAdapter)
  - oidc:   Authorization Code + PKCE → JWT dell'identity provider (OidcAuthClient)

Il flusso OIDC è **stateless lato server**: begin_oidc_flow_stateless() restituisce
l'URL di autorizzazione e i parametri (state, nonce, code_verifier) che il chiamante
conserva (sessione firmata per la Web App, client per la SPA/REST) e rimanda a
complete_oidc_flow(), che completa lo scambio e ritorna la Person autenticata.
Nessuno stato è mantenuto nel processo: il flusso funziona con più worker.
"""
from __future__ import annotations

import secrets
from typing import Optional, Tuple
from uuid import UUID

# Livello ACL assegnato al primo amministratore creato dal flusso di primo
# avvio. Nella convenzione del sistema ACL (DESIGN §10) un numero più basso è
# più privilegiato: 0 è il tier amministrativo massimo, che soddisfa le entry
# `MANAGE_ACL`/`MANAGE_PROFILES` seminate al bootstrap. Il rilevamento
# "esiste già un admin" (backend OIDC) usa questa soglia.
INITIAL_ADMIN_ACL_LEVEL = 0
# Lunghezza minima password, allineata al vincolo di LocalAuthAdapter.set_password.
_INITIAL_ADMIN_MIN_PASSWORD_LEN = 12

from ...domain.acl import Profile
from ...domain.entities import Person
from ...domain.exceptions import AuthenticationError, NotFoundError, ValidationError
from ._shared import acl_bypass, transactional


class AuthService:

    def __init__(
        self,
        person_repo,
        local_auth=None,
        oidc_client=None,
        oidc_redirect_uri: Optional[str] = None,
        person_backend: str = "local",
        auth_backend: str = "local",
        oidc_auto_provision_local: bool = False,
        password_min_length: int = _INITIAL_ADMIN_MIN_PASSWORD_LEN,
        password_require_uppercase: bool = True,
        password_require_digit: bool = True,
        password_require_special: bool = True,
        uow=None,
    ) -> None:
        self._person_repo = person_repo
        self._local_auth = local_auth
        self._oidc_client = oidc_client
        self._oidc_redirect_uri = oidc_redirect_uri
        self._person_backend = person_backend
        self._auth_backend = auth_backend
        self._oidc_auto_provision_local = oidc_auto_provision_local
        self._password_min_length = password_min_length
        self._password_require_uppercase = password_require_uppercase
        self._password_require_digit = password_require_digit
        self._password_require_special = password_require_special
        self._uow = uow

    # ------------------------------------------------------------------
    # Autenticazione locale
    # ------------------------------------------------------------------

    def login_local(self, username: str, password: str) -> Tuple[Person, str]:
        """Verifica le credenziali tramite nickname e restituisce (Person, access_token).

        Non decorato con ``@transactional``: l'adapter apre transazioni proprie
        così che il conteggio dei tentativi falliti persista anche quando il
        login fallisce (un rollback del caso d'uso lo annullerebbe).
        """
        if not self._local_auth:
            raise AuthenticationError("Autenticazione locale non configurata (auth_backend != local)")
        return self._local_auth.authenticate(username, password)

    @transactional
    def set_password(
        self, person_id: UUID, password: str, must_change: bool = False
    ) -> None:
        if not self._local_auth:
            raise AuthenticationError("Autenticazione locale non configurata")
        self._local_auth.set_password(person_id, password, must_change=must_change)

    @transactional
    def password_change_required(self, person_id: UUID) -> bool:
        """True se l'operatore deve cambiare la password al prossimo accesso.

        Sempre False con backend OIDC (nessuna credenziale locale gestita).
        """
        if not self._local_auth:
            return False
        return self._local_auth.password_change_required(person_id)

    @transactional
    def delete_credentials(self, person_id: UUID) -> bool:
        if not self._local_auth:
            return False
        return self._local_auth.delete_credentials(person_id)

    # ------------------------------------------------------------------
    # Primo avvio: creazione dell'amministratore iniziale
    # ------------------------------------------------------------------

    def _is_local_backend(self) -> bool:
        """True quando persone/gruppi sono gestiti localmente."""
        return self._person_backend == "local"

    @transactional
    def admin_exists(self, person_service) -> bool:
        """Indica se il sistema è già stato inizializzato con un amministratore.

        - Backend locale con auth locale: True se esiste almeno una Person (il
          primo utente creato è sempre l'admin; il database parte vuoto).
        - Backend locale con auth OIDC: True; il primo callback OIDC crea
          l'admin iniziale senza passare dalle admin API dell'IdP.
        - Backend persone OIDC: True se nell'IdP esiste almeno una Person con
          ``acl_level <= INITIAL_ADMIN_ACL_LEVEL`` (livello più basso = più
          privilegiato).
        """
        with acl_bypass():
            if self._oidc_auto_provision_local:
                # In auth OIDC + persone locali non esiste un setup anonimo con
                # password locale: il primo login OIDC auto-provisiona l'admin.
                return True
            if self._is_local_backend():
                return bool(person_service.list({}))
            return any(
                p.acl_level <= INITIAL_ADMIN_ACL_LEVEL
                for p in person_service.list({})
            )

    @transactional
    def create_initial_admin(self, person_service, nickname: str, password: str) -> Person:
        """Crea l'amministratore iniziale (ACL ``INITIAL_ADMIN_ACL_LEVEL``).

        È l'unico flusso anonimo ammesso: il chiamante deve aver già verificato
        con :meth:`admin_exists` che nessun amministratore sia presente.

        - Backend locale + auth locale: crea la Person e imposta le credenziali
          nella stessa unità di lavoro (atomico via rollback).
        - Backend locale + auth OIDC: non usa il setup anonimo; il primo admin
          viene creato dal callback OIDC.
        - Backend persone OIDC: delega creazione utente e impostazione password
          all'identity provider tramite la sua admin API.
        """
        if self._is_local_backend():
            return self._create_initial_local_admin(person_service, nickname, password)
        return self._create_initial_oidc_admin(person_service, nickname, password)

    def _create_initial_local_admin(self, person_service, nickname: str, password: str) -> Person:
        if self._auth_backend == "oidc":
            raise AuthenticationError(
                "Con autenticazione OIDC e persone locali il primo amministratore "
                "viene creato dal primo login OIDC"
            )
        with acl_bypass():
            person_dto = person_service.add([nickname])
            person_service.set_acl_profile(person_dto.id, acl_level=INITIAL_ADMIN_ACL_LEVEL)
        self.set_password(UUID(person_dto.id), password)
        return self._person_repo.get(UUID(person_dto.id))

    def _validate_initial_password(self, password: str) -> None:
        if len(password.encode("utf-8")) > 72:
            raise ValidationError(
                "La password non può superare 72 byte UTF-8", field="password"
            )
        if not password or len(password) < self._password_min_length:
            raise ValidationError(
                f"La password deve avere almeno {self._password_min_length} caratteri",
                field="password",
            )
        if self._password_require_uppercase and not any(c.isupper() for c in password):
            raise ValidationError(
                "La password deve contenere almeno una lettera maiuscola",
                field="password",
            )
        if self._password_require_digit and not any(c.isdigit() for c in password):
            raise ValidationError("La password deve contenere almeno una cifra", field="password")
        if self._password_require_special and not any(
            not c.isalnum() and not c.isspace() for c in password
        ):
            raise ValidationError(
                "La password deve contenere almeno un carattere speciale",
                field="password",
            )

    def _create_initial_oidc_admin(self, person_service, nickname: str, password: str) -> Person:
        set_password = getattr(self._person_repo, "set_password", None)
        if not callable(set_password):
            raise AuthenticationError(
                "Il backend Person OIDC non supporta l'impostazione della password"
            )
        self._validate_initial_password(password)
        # La creazione dell'utente è una POST all'IdP: non è transazionale, quindi
        # in caso di fallimento successivo va compensata con una delete esplicita
        # per non lasciare un account orfano senza password.
        with acl_bypass():
            person_dto = person_service.add([nickname])
            person_service.set_acl_profile(person_dto.id, acl_level=INITIAL_ADMIN_ACL_LEVEL)
        person_id = UUID(person_dto.id)
        try:
            set_password(person_id, password)
        except Exception:
            try:
                self._person_repo.delete(person_id)
            except Exception:
                pass
            raise
        return self._person_repo.get(person_id)

    def logout_local(self, token: str) -> None:
        """Revoca un token locale (jti in blacklist).

        Con backend OIDC non c'è nulla da revocare lato applicazione: gli access
        token sono JWT stateless validati via firma e restano validi fino alla
        scadenza. Per la Web App il logout federato passa invece da
        :meth:`build_oidc_logout_url`, quando l'IdP espone ``end_session_endpoint``.
        """
        if self._local_auth:
            self._local_auth.revoke_token(token)

    # ------------------------------------------------------------------
    # Flusso OIDC (stateless — Web App via sessione firmata, SPA/REST via client)
    # ------------------------------------------------------------------

    def begin_oidc_flow(
        self,
        redirect_uri: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> dict:
        """Avvia il flusso OIDC PKCE senza mantenere stato lato server.

        Restituisce ``{ url, state, nonce, code_verifier }``. Il chiamante deve
        conservare state, nonce e code_verifier (sessione firmata per la Web App,
        client per la SPA) e rimandarli a :meth:`complete_oidc_flow`. Funziona con
        deployment multi-worker perché non c'è stato condiviso nel processo.
        """
        if not self._oidc_client:
            raise AuthenticationError("OIDC non configurato (auth_backend != oidc)")
        from ...infrastructure.auth.oidc_client import OidcAuthClient
        code_verifier, state = OidcAuthClient.generate_pkce_pair()
        nonce = secrets.token_urlsafe(16)
        uri = redirect_uri or self._oidc_redirect_uri or ""
        auth_url = self._oidc_client.build_auth_url(
            redirect_uri=uri,
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            prompt=prompt,
        )
        return {
            "url": auth_url,
            "state": state,
            "nonce": nonce,
            "code_verifier": code_verifier,
        }

    # Alias storico mantenuto per i client SPA esistenti.
    begin_oidc_flow_stateless = begin_oidc_flow

    def build_oidc_logout_url(
        self,
        post_logout_redirect_uri: str = "",
        id_token_hint: Optional[str] = None,
    ) -> Optional[str]:
        """URL di logout lato IdP, se il provider espone end_session_endpoint."""
        if not self._oidc_client:
            return None
        builder = getattr(self._oidc_client, "build_logout_url", None)
        if not callable(builder):
            return None
        return builder(
            post_logout_redirect_uri=post_logout_redirect_uri,
            id_token_hint=id_token_hint,
        )

    @transactional
    def complete_oidc_flow(
        self,
        code: str,
        state: str,
        nonce: str,
        code_verifier: str,
        redirect_uri: Optional[str] = None,
    ) -> Tuple[Person, object]:
        """Completa il flusso OIDC a partire dai parametri conservati dal chiamante.

        ``state`` va confrontato dal chiamante (sessione/client) prima di invocare
        questo metodo; ``nonce`` e ``code_verifier`` sono obbligatori.

        Restituisce (Person, OidcTokenSet).
        """
        if not self._oidc_client:
            raise AuthenticationError("OIDC non configurato")
        if not nonce or not code_verifier:
            raise AuthenticationError("Parametri OIDC mancanti (nonce/code_verifier)")

        uri = redirect_uri or self._oidc_redirect_uri or ""
        token_set = self._oidc_client.exchange_code(code, uri, code_verifier)

        claims = self._oidc_client.validate_id_token(token_set.id_token, nonce)
        sub = claims.get("sub", "")
        if not sub:
            raise AuthenticationError("ID token privo del claim 'sub'")
        resolver = getattr(self._person_repo, "resolve_external_subject", None)
        if callable(resolver):
            person_id = resolver(str(sub))
        else:
            try:
                person_id = UUID(sub)
            except ValueError:
                raise AuthenticationError(
                    f"OIDC sub non è un UUID valido: {sub!r}"
                ) from None

        try:
            person = self._person_repo.get(person_id)
        except NotFoundError:
            if not self._oidc_auto_provision_local:
                raise AuthenticationError("Utente OIDC non registrato") from None
            person = self._provision_local_oidc_person(person_id, claims)
        return person, token_set

    def _provision_local_oidc_person(self, person_id: UUID, claims: dict) -> Person:
        nickname = (
            claims.get("preferred_username")
            or claims.get("name")
            or claims.get("email")
            or claims.get("sub")
            or str(person_id)
        )
        profile = self._profile_from_oidc_claims(claims)
        if profile is None:
            is_first_person = not self._person_repo.list({})
            profile = Profile(
                level=INITIAL_ADMIN_ACL_LEVEL if is_first_person else Profile().level
            )
        person = Person(id=person_id, nicknames=[str(nickname)], acl=profile)
        person.validate()
        self._person_repo.save(person)
        return person

    @staticmethod
    def _profile_from_oidc_claims(claims: dict) -> Optional[Profile]:
        level = claims.get("acl_level")
        groups = claims.get("acl_groups")
        if level is None:
            return None
        if isinstance(groups, str):
            groups = [g.strip() for g in groups.split(",") if g.strip()]
        try:
            return Profile(
                level=int(level),
                groups=frozenset(str(g) for g in (groups or [])),
            )
        except (TypeError, ValueError, ValidationError):
            return None
