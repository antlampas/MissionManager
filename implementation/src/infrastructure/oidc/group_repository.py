# SPDX-License-Identifier: CC-BY-SA-4.0
"""OidcGroupRepository — persiste Group tramite le API admin di Authentik o Keycloak."""
from __future__ import annotations

from uuid import UUID

import requests

from ...infrastructure.group_repository import GroupRepositoryAdapter
from ...domain.entities import Group, Zone
from ...domain.enums import ZoneType
from ...domain.exceptions import NotFoundError
from ..repositories.external_identity_repository import SqlAlchemyExternalIdentityRepository
from ._pagination import collect_pages


class OidcGroupRepository(GroupRepositoryAdapter):

    def __init__(
        self,
        oidc_url: str,
        admin_token: str,
        provider: str = "authentik",
        identity_repo: SqlAlchemyExternalIdentityRepository | None = None,
        verify: bool | str = True,
    ) -> None:
        self._base = oidc_url.rstrip("/")
        self._token = admin_token
        self._provider = provider
        # Policy TLS verso l'admin API dell'IdP (vedi OidcPersonRepository).
        self._verify = verify
        if identity_repo is None:
            raise ValueError("identity_repo è obbligatorio per il backend OIDC")
        self._identities = identity_repo

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _groups_url(self) -> str:
        if self._provider == "authentik":
            return f"{self._base}/core/groups/"
        return f"{self._base}/groups/"

    def _users_url(self) -> str:
        if self._provider == "authentik":
            return f"{self._base}/core/users/"
        return f"{self._base}/users/"

    def _row_to_group(self, data: dict) -> Group:
        gid = self._identities.internal_id(
            self._provider,
            "group",
            str(data["pk"] if self._provider == "authentik" else data["id"]),
        )
        attrs = data.get("attributes", {}) or {}
        zone: Zone | None = None
        if "zone_id" in attrs:
            try:
                zone = Zone(
                    id=UUID(attrs["zone_id"]),
                    type=ZoneType(attrs.get("zone_type", "VIRTUAL")),
                    name=attrs.get("zone_name", ""),
                    description=attrs.get("zone_description"),
                )
            except (KeyError, ValueError):
                zone = None
        return Group(id=gid, zone=zone)

    def _group_to_payload(self, entity: Group) -> dict:
        attrs: dict = {}
        name = str(entity.id)
        if entity.zone:
            name = entity.zone.name or name
            attrs = {
                "zone_id": str(entity.zone.id),
                "zone_type": entity.zone.type.value,
                "zone_name": entity.zone.name,
                "zone_description": entity.zone.description,
            }
        return {"name": name, "attributes": attrs}

    def _external_id(self, internal_id: UUID) -> str:
        external_id = self._identities.external_id(
            self._provider, "group", internal_id
        )
        if external_id is None:
            raise NotFoundError(
                f"Group {internal_id} non trovato",
                resource_type="group",
                resource_id=internal_id,
            )
        return external_id

    def _person_external_id(self, internal_id: UUID) -> str:
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
        raise RuntimeError("Il provider OIDC non ha restituito l'identificatore del gruppo creato")

    def get(self, id: UUID) -> Group:
        url = f"{self._groups_url()}{self._external_id(id)}/"
        resp = requests.get(url, headers=self._headers(), timeout=10, verify=self._verify)
        if resp.status_code == 404:
            raise NotFoundError(f"Group {id} non trovato", resource_type="group", resource_id=id)
        resp.raise_for_status()
        return self._row_to_group(resp.json())

    def list(self, filters: dict) -> list[Group]:
        rows = collect_pages(
            requests, self._provider, self._groups_url(), self._headers(),
            verify=self._verify,
        )
        return [self._row_to_group(r) for r in rows]

    def save(self, entity: Group) -> Group:
        payload = self._group_to_payload(entity)
        external_id = self._identities.external_id(self._provider, "group", entity.id)
        if external_id is None:
            resp = requests.post(self._groups_url(), json=payload, headers=self._headers(), timeout=10, verify=self._verify)
            resp.raise_for_status()
            self._identities.bind(
                self._provider, "group", self._created_subject(resp), entity.id
            )
            return entity
        url = f"{self._groups_url()}{external_id}/"
        resp = requests.patch(url, json=payload, headers=self._headers(), timeout=10, verify=self._verify)
        resp.raise_for_status()
        return entity

    def delete(self, id: UUID) -> bool:
        external_id = self._identities.external_id(self._provider, "group", id)
        if external_id is None:
            return False
        url = f"{self._groups_url()}{external_id}/"
        resp = requests.delete(url, headers=self._headers(), timeout=10, verify=self._verify)
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        self._identities.delete(self._provider, "group", id)
        return True

    def exists(self, id: UUID) -> bool:
        external_id = self._identities.external_id(self._provider, "group", id)
        if external_id is None:
            return False
        url = f"{self._groups_url()}{external_id}/"
        resp = requests.get(url, headers=self._headers(), timeout=10, verify=self._verify)
        return resp.status_code == 200

    def add_member(self, group_id: UUID, person_id: UUID) -> None:
        group_external_id = self._external_id(group_id)
        person_external_id = self._person_external_id(person_id)
        if self._provider == "authentik":
            url = f"{self._groups_url()}{group_external_id}/add_user/"
            resp = requests.post(
                url,
                json={"pk": int(person_external_id)},
                headers=self._headers(),
                timeout=10,
                verify=self._verify,
            )
        else:
            url = f"{self._users_url()}{person_external_id}/groups/{group_external_id}"
            resp = requests.put(url, headers=self._headers(), timeout=10, verify=self._verify)
        if resp.status_code == 404:
            raise NotFoundError(
                f"Group {group_id} o Person {person_id} non trovati",
                resource_type="group_member",
                resource_id=group_id,
            )
        resp.raise_for_status()

    def remove_member(self, group_id: UUID, person_id: UUID) -> None:
        group_external_id = self._external_id(group_id)
        person_external_id = self._person_external_id(person_id)
        if self._provider == "authentik":
            url = f"{self._groups_url()}{group_external_id}/remove_user/"
            resp = requests.post(
                url,
                json={"pk": int(person_external_id)},
                headers=self._headers(),
                timeout=10,
                verify=self._verify,
            )
        else:
            url = f"{self._users_url()}{person_external_id}/groups/{group_external_id}"
            resp = requests.delete(url, headers=self._headers(), timeout=10, verify=self._verify)
        if resp.status_code == 404:
            raise NotFoundError(
                f"Group {group_id} o Person {person_id} non trovati",
                resource_type="group_member",
                resource_id=group_id,
            )
        resp.raise_for_status()
