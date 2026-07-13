# SPDX-License-Identifier: CC-BY-SA-4.0
"""OidcPersonRepository — persiste Person tramite le API admin di Authentik o Keycloak."""
from __future__ import annotations

import logging
import time
from typing import Optional
from uuid import UUID

import requests

from ...infrastructure.person_repository import PersonRepositoryAdapter
from ...domain.acl import ANON_SENTINEL, Profile
from ...domain.entities import Person
from ...domain.exceptions import AuthenticationError, AuthorizationError, NotFoundError
from ..repositories.external_identity_repository import SqlAlchemyExternalIdentityRepository
from ._pagination import collect_pages

logger = logging.getLogger(__name__)


class OidcPersonRepository(PersonRepositoryAdapter):
    """Reads and writes Person objects via the OIDC provider admin REST API.

    Authentik base URL:  https://auth.internal/api/v3
    Keycloak base URL:   https://auth.internal/admin/realms/{realm}

    Il Profile ACL è letto dagli attributi utente custom dell'IdP:
      acl_level (int, più basso = più privilegiato), acl_groups (lista di str).

    Le identità sono sempre legate (in ``mm_external_identities``) tramite il
    *path-id* usato dall'admin API (``pk`` per Authentik, ``id`` per Keycloak).
    Quando il claim ``sub`` del token non coincide con quel path-id (es.
    Authentik con Subject mode "uuid"), ``subject_field`` indica il campo utente
    a cui il ``sub`` corrisponde e ``resolve_external_subject`` traduce il ``sub``
    nel path-id interrogando l'IdP, mantenendo letture e login coerenti.
    """

    def __init__(
        self,
        oidc_url: str,
        admin_token: str,
        provider: str = "authentik",
        identity_repo: SqlAlchemyExternalIdentityRepository | None = None,
        subject_field: Optional[str] = None,
        cache_ttl: int = 30,
        verify: bool | str = True,
    ) -> None:
        self._base = oidc_url.rstrip("/")
        self._token = admin_token
        self._provider = provider  # "authentik" | "keycloak"
        # Policy TLS verso l'admin API dell'IdP: True (default), False (solo
        # sviluppo) o path a un CA bundle custom — stessa semantica di
        # ``security.persons.verify_tls``/``ca_bundle`` (OidcAuthClient).
        self._verify = verify
        if identity_repo is None:
            raise ValueError("identity_repo è obbligatorio per il backend OIDC")
        self._identities = identity_repo
        self._subject_field = subject_field
        self._cache_ttl = cache_ttl
        # id interno → (Person, scadenza monotonic): cache a TTL breve su get() (P4)
        self._cache: dict[UUID, tuple[Person, float]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path_id_field(self) -> str:
        """Campo JSON usato come identificatore nel path dell'admin API."""
        return "pk" if self._provider == "authentik" else "id"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _users_url(self) -> str:
        if self._provider == "authentik":
            return f"{self._base}/core/users/"
        return f"{self._base}/users/"

    def _groups_url(self) -> str:
        if self._provider == "authentik":
            return f"{self._base}/core/groups/"
        return f"{self._base}/groups/"

    def _row_to_person(self, data: dict) -> Person:
        attrs = data.get("attributes", {}) or {}
        level = attrs.get("acl_level")
        groups = attrs.get("acl_groups")
        if level is None and not groups:
            logger.info(
                "Utente OIDC '%s' senza attributi acl_level/acl_groups: "
                "riceve il profilo meno privilegiato (default-deny).",
                data.get("username", "<sconosciuto>"),
            )
        if isinstance(groups, str):
            groups = [g.strip() for g in groups.split(",") if g.strip()]
        return Person(
            id=self._identities.internal_id(
                self._provider, "person", self._subject(data)
            ),
            nicknames=[data.get("username", "")],
            acl=Profile(
                level=int(level) if level is not None else ANON_SENTINEL,
                groups=frozenset(str(g) for g in (groups or [])),
            ),
        )

    def _subject(self, data: dict) -> str:
        """Path-id dell'utente, chiave canonica dei binding di identità."""
        return str(data[self._path_id_field()])

    def _external_id(self, internal_id: UUID) -> str:
        external_id = self._identities.external_id(
            self._provider, "person", internal_id
        )
        if external_id is None:
            raise NotFoundError(
                f"Person {internal_id} non trovata",
                resource_type="person",
                resource_id=internal_id,
            )
        return external_id

    def resolve_external_subject(self, subject: str) -> UUID:
        """Riconcilia il claim ``sub`` OIDC con l'UUID interno del dominio.

        I binding sono sempre chiavati sul path-id dell'admin API. Se ``sub`` non
        coincide con quel path-id (``subject_field`` impostato e diverso dal
        campo path-id), traduce ``sub`` nel path-id interrogando l'IdP, così che
        login e letture condividano lo stesso identificatore interno.
        """
        subject = str(subject)
        field = self._subject_field
        if not field or field == self._path_id_field():
            # sub == path-id (Keycloak; Authentik con Subject mode "user_id")
            return self._identities.internal_id(self._provider, "person", subject)
        path_id = self._path_id_for_subject(field, subject)
        return self._identities.internal_id(self._provider, "person", path_id)

    def _path_id_for_subject(self, field: str, subject: str) -> str:
        """Trova il path-id dell'utente il cui campo ``field`` vale ``subject``."""
        try:
            rows = collect_pages(
                requests,
                self._provider,
                self._users_url(),
                self._headers(),
                {field: subject},
                verify=self._verify,
            )
        except (AuthenticationError, AuthorizationError):
            raise
        except Exception as exc:
            raise AuthenticationError(
                "Subject OIDC non risolvibile tramite admin API "
                f"({field}={subject!r}). Verifica MISSIONMANAGER_OIDC_SUBJECT_FIELD "
                "e il Subject mode del provider: con Authentik il subject deve "
                "coincidere con il path-id utente oppure con un campo filtrabile "
                "come uuid/username/email. Per usare OIDC solo per il login, "
                "configura person_backend=local e auth_backend=oidc."
            ) from exc
        matches = [r for r in rows if str(r.get(field)) == subject]
        if not matches:
            raise AuthenticationError(
                f"Nessun utente OIDC con {field}={subject}: token non risolvibile. "
                "Per usare OIDC solo per il login, configura person_backend=local "
                "e auth_backend=oidc."
            )
        return self._subject(matches[0])

    def set_password(self, person_id: UUID, password: str) -> None:
        """Imposta la password dell'utente delegando all'admin API dell'IdP.

        Usato dal flusso di primo avvio OIDC per creare l'amministratore
        iniziale già provvisto di credenziali utilizzabili al login.
        """
        external_id = self._external_id(person_id)
        if self._provider == "authentik":
            url = f"{self._users_url()}{external_id}/set_password/"
            resp = requests.post(
                url,
                json={"password": password},
                headers=self._headers(),
                timeout=10,
                verify=self._verify,
            )
        else:  # keycloak
            url = f"{self._users_url()}{external_id}/reset-password"
            resp = requests.put(
                url,
                json={"type": "password", "value": password, "temporary": False},
                headers=self._headers(),
                timeout=10,
                verify=self._verify,
            )
        resp.raise_for_status()

    @staticmethod
    def _created_subject(response: requests.Response) -> str:
        try:
            body = response.json()
            if isinstance(body, dict):
                subject = body.get("pk", body.get("id"))
                if subject is not None:
                    return str(subject)
        except ValueError:
            pass
        location = response.headers.get("Location", "").rstrip("/")
        if location:
            return location.rsplit("/", 1)[-1]
        raise RuntimeError("Il provider OIDC non ha restituito l'identificatore dell'utente creato")

    def _person_to_payload(self, entity: Person) -> dict:
        payload: dict = {
            "username": entity.nicknames[0] if entity.nicknames else str(entity.id),
            "name": entity.nicknames[0] if entity.nicknames else "",
            "attributes": {
                "acl_level": entity.acl.level,
                "acl_groups": entity.acl.stored_groups(),
                "nicknames": entity.nicknames,
            },
        }
        return payload

    # ------------------------------------------------------------------
    # BaseRepository protocol
    # ------------------------------------------------------------------

    def get(self, id: UUID) -> Person:
        cached = self._cache_get(id)
        if cached is not None:
            return cached
        external_id = self._external_id(id)
        url = f"{self._users_url()}{external_id}/"
        resp = requests.get(url, headers=self._headers(), timeout=10, verify=self._verify)
        if resp.status_code == 404:
            raise NotFoundError(f"Person {id} non trovata", resource_type="person", resource_id=id)
        resp.raise_for_status()
        data = resp.json()
        # Keycloak returns a list for GET /users?id=...; handle both
        if isinstance(data, list):
            if not data:
                raise NotFoundError(f"Person {id} non trovata", resource_type="person", resource_id=id)
            data = data[0]
        person = self._row_to_person(data)
        self._cache_put(id, person)
        return person

    # ------------------------------------------------------------------
    # Cache a TTL breve (P4) — riduce i round-trip all'admin API per richiesta
    # ------------------------------------------------------------------

    def _cache_get(self, id: UUID) -> Optional[Person]:
        if self._cache_ttl <= 0:
            return None
        entry = self._cache.get(id)
        if entry is None:
            return None
        person, expiry = entry
        if time.monotonic() >= expiry:
            self._cache.pop(id, None)
            return None
        return person

    def _cache_put(self, id: UUID, person: Person) -> None:
        if self._cache_ttl > 0:
            self._cache[id] = (person, time.monotonic() + self._cache_ttl)

    def _cache_invalidate(self, id: UUID) -> None:
        self._cache.pop(id, None)

    def list(self, filters: dict) -> list[Person]:
        rows = collect_pages(
            requests, self._provider, self._users_url(), self._headers(),
            verify=self._verify,
        )
        return [self._row_to_person(r) for r in rows]

    def save(self, entity: Person) -> Person:
        payload = self._person_to_payload(entity)
        external_id = self._identities.external_id(self._provider, "person", entity.id)
        if external_id is None:
            resp = requests.post(
                self._users_url(),
                json=payload,
                headers=self._headers(),
                timeout=10,
                verify=self._verify,
            )
            resp.raise_for_status()
            self._identities.bind(
                self._provider, "person", self._created_subject(resp), entity.id
            )
            return entity
        url = f"{self._users_url()}{external_id}/"
        resp = requests.patch(url, json=payload, headers=self._headers(), timeout=10, verify=self._verify)
        resp.raise_for_status()
        self._cache_invalidate(entity.id)
        return entity

    def delete(self, id: UUID) -> bool:
        external_id = self._identities.external_id(self._provider, "person", id)
        if external_id is None:
            return False
        url = f"{self._users_url()}{external_id}/"
        resp = requests.delete(url, headers=self._headers(), timeout=10, verify=self._verify)
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        self._identities.delete(self._provider, "person", id)
        self._cache_invalidate(id)
        return True

    def exists(self, id: UUID) -> bool:
        external_id = self._identities.external_id(self._provider, "person", id)
        if external_id is None:
            return False
        url = f"{self._users_url()}{external_id}/"
        resp = requests.get(url, headers=self._headers(), timeout=10, verify=self._verify)
        return resp.status_code == 200

    def get_by_nickname(self, nickname: str) -> Optional[Person]:
        rows = collect_pages(
            requests,
            self._provider,
            self._users_url(),
            self._headers(),
            {"username": nickname},
            verify=self._verify,
        )
        matches = [r for r in rows if r.get("username") == nickname]
        return self._row_to_person(matches[0]) if matches else None

    def get_by_group(self, group_id: UUID) -> list[Person]:
        if self._provider == "authentik":
            group_external_id = self._identities.external_id(
                self._provider, "group", group_id
            )
            if group_external_id is None:
                return []
            url = f"{self._groups_url()}{group_external_id}/"
            resp = requests.get(url, headers=self._headers(), timeout=10, verify=self._verify)
            resp.raise_for_status()
            members = resp.json().get("users_obj", [])
            return [self._row_to_person(m) for m in members]
        else:
            # Keycloak: /admin/realms/{realm}/groups/{id}/members
            group_external_id = self._identities.external_id(
                self._provider, "group", group_id
            )
            if group_external_id is None:
                return []
            url = f"{self._groups_url()}{group_external_id}/members"
            members = collect_pages(
                requests, self._provider, url, self._headers(), verify=self._verify
            )
            return [self._row_to_person(m) for m in members]
