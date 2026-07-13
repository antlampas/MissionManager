# SPDX-License-Identifier: CC-BY-SA-4.0
"""Verifica end-to-end: gestione utenti + ACL in modalità OIDC.

Diversamente da ``test_oidc_flows`` (che sonda i singoli adapter con risposte
HTTP predefinite), qui si guida l'intera catena applicativa con un IdP finto
*stateful* (stile Authentik): gli utenti creati vengono davvero memorizzati e
riletti, così i round-trip di ``PersonService`` e la decisione di
``AuthorizationPolicy`` sono significativi.

Si dimostra che:
  1. ``PersonService`` esegue il CRUD delle persone contro le admin API dell'IdP
     (create → read → list → get_by_nickname → delete).
  2. ``set_acl_profile`` persiste livello e gruppi ACL negli attributi utente
     dell'IdP e la rilettura li riflette.
  3. ``AuthorizationPolicy`` — con ``PersonProfileProvider`` sopra il repository
     OIDC e ``AclEntry`` persistite in locale — autorizza in base al profilo
     letto dall'IdP, esattamente come col backend locale.

Nessuna rete reale: ``requests`` è sostituito da un fake stateful; le AclEntry e
i binding di identità usano SQLite in-memory (fixture ``fk_session``).
"""
from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass

import pytest

from src.application.authorization import AuthorizationPolicy
from src.application.services.person_service import PersonService
from src.domain.acl import (
    ANON_SENTINEL,
    AclEntry,
    JoinOp,
    Operation,
    Permission,
    ResourceRef,
    SubjectRef,
)
from src.domain.enums import ResourceType
from src.infrastructure.acl import PersonProfileProvider
from src.infrastructure.oidc import group_repository as gr_mod
from src.infrastructure.oidc import person_repository as pr_mod
from src.infrastructure.oidc.group_repository import OidcGroupRepository
from src.infrastructure.oidc.person_repository import OidcPersonRepository
from src.infrastructure.repositories.acl_entry_repository import SqlAlchemyAclEntryRepository
from src.infrastructure.repositories.external_identity_repository import (
    SqlAlchemyExternalIdentityRepository,
)
from src.infrastructure.repositories.session import (
    SqlAlchemySessionProvider,
    SqlAlchemyUnitOfWork,
)


# --------------------------------------------------------------------------
# IdP finto stateful (stile Authentik: /core/users/)
# --------------------------------------------------------------------------

class _Resp:
    def __init__(self, json_data=None, status_code=200, headers=None):
        self._json = json_data
        self.status_code = status_code
        self.headers = headers or {}
        self.ok = 200 <= status_code < 300

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class _StatefulAuthentik:
    """Fake di ``requests`` che tiene davvero lo stato utenti/gruppi dell'IdP."""

    _USER_MARKER = "/core/users/"
    _GROUP_MARKER = "/core/groups/"

    def __init__(self, page_size: int = 20) -> None:
        self.users: dict[int, dict] = {}
        self.groups: dict[int, dict] = {}
        self._ids = itertools.count(1)
        self._page_size = page_size
        self.calls = {"get": 0, "post": 0, "patch": 0, "delete": 0}

    def _parse(self, url: str, marker: str) -> tuple[int | None, str | None]:
        """Restituisce (pk, azione) dal path dopo il marker Authentik."""
        tail = url.split(marker, 1)[1].strip("/")
        if not tail:
            return None, None
        parts = tail.split("/")
        return int(parts[0]), (parts[1] if len(parts) > 1 else None)

    def _paged(self, rows: list[dict], params: dict | None):
        params = dict(params or {})
        page = int(params.pop("page", 1))
        for key, value in params.items():
            rows = [r for r in rows if str(r.get(key)) == str(value)]
        total_pages = max(1, (len(rows) + self._page_size - 1) // self._page_size)
        start = (page - 1) * self._page_size
        chunk = rows[start : start + self._page_size]
        return _Resp(
            {"results": chunk, "pagination": {"current": page, "total_pages": total_pages}},
            200,
        )

    def get(self, url, params=None, headers=None, timeout=None, verify=True):
        self.calls["get"] += 1
        if self._GROUP_MARKER in url:
            pk, _ = self._parse(url, self._GROUP_MARKER)
            if pk is None:
                return self._paged(list(self.groups.values()), params)
            row = self.groups.get(pk)
            return _Resp(row, 200) if row is not None else _Resp(None, 404)
        pk, _ = self._parse(url, self._USER_MARKER)
        if pk is None:
            # Emula la paginazione Authentik: ``?page=`` + envelope ``pagination``.
            return self._paged(list(self.users.values()), params)
        row = self.users.get(pk)
        return _Resp(row, 200) if row is not None else _Resp(None, 404)

    def post(self, url, json=None, headers=None, timeout=None, verify=True):
        self.calls["post"] += 1
        if self._GROUP_MARKER in url:
            pk, action = self._parse(url, self._GROUP_MARKER)
            if action == "add_user":
                user = self.users[int(json["pk"])]
                members = self.groups[pk].setdefault("users_obj", [])
                if all(m["pk"] != user["pk"] for m in members):
                    members.append(user)
                return _Resp({}, 204)
            if action == "remove_user":
                user_pk = int(json["pk"])
                members = self.groups[pk].setdefault("users_obj", [])
                self.groups[pk]["users_obj"] = [
                    m for m in members if m["pk"] != user_pk
                ]
                return _Resp({}, 204)
            new_pk = next(self._ids)
            row = dict(json or {})
            row["pk"] = new_pk
            row.setdefault("users_obj", [])
            self.groups[new_pk] = row
            return _Resp(row, 201)
        pk, action = self._parse(url, self._USER_MARKER)
        if action == "set_password":
            self.users[pk]["_password"] = json["password"]
            return _Resp({}, 204)
        new_pk = next(self._ids)
        row = dict(json or {})
        row["pk"] = new_pk
        self.users[new_pk] = row
        return _Resp(row, 201)

    def patch(self, url, json=None, headers=None, timeout=None, verify=True):
        self.calls["patch"] += 1
        if self._GROUP_MARKER in url:
            pk, _ = self._parse(url, self._GROUP_MARKER)
            if pk not in self.groups:
                return _Resp(None, 404)
            self.groups[pk].update(json or {})
            return _Resp(self.groups[pk], 200)
        pk, _ = self._parse(url, self._USER_MARKER)
        if pk not in self.users:
            return _Resp(None, 404)
        # Authentik sostituisce in blocco gli attributi inviati.
        self.users[pk].update(json or {})
        return _Resp(self.users[pk], 200)

    def delete(self, url, params=None, headers=None, timeout=None, verify=True):
        self.calls["delete"] += 1
        if self._GROUP_MARKER in url:
            pk, _ = self._parse(url, self._GROUP_MARKER)
            if pk not in self.groups:
                return _Resp(None, 404)
            del self.groups[pk]
            return _Resp(None, 204)
        pk, _ = self._parse(url, self._USER_MARKER)
        if pk not in self.users:
            return _Resp(None, 404)
        del self.users[pk]
        return _Resp(None, 204)


# --------------------------------------------------------------------------
# Fixture: sistema OIDC "reale" su SQLite in-memory + IdP finto
# --------------------------------------------------------------------------

class _NoHierarchy:
    """Le risorse radice di tipo non hanno padri: la gerarchia non è consultata."""

    def parents_of(self, resource):
        return []


@dataclass
class _OidcSystem:
    person: PersonService
    person_repo: OidcPersonRepository
    group_repo: OidcGroupRepository
    policy: AuthorizationPolicy
    entry_repo: SqlAlchemyAclEntryRepository
    uow: SqlAlchemyUnitOfWork
    idp: _StatefulAuthentik


@pytest.fixture
def oidc_system(fk_session, monkeypatch) -> _OidcSystem:
    idp = _StatefulAuthentik()
    monkeypatch.setattr(pr_mod, "requests", idp)
    monkeypatch.setattr(gr_mod, "requests", idp)

    sessions = SqlAlchemySessionProvider(fk_session)
    uow = SqlAlchemyUnitOfWork(sessions)
    identities = SqlAlchemyExternalIdentityRepository(sessions)

    person_repo = OidcPersonRepository(
        oidc_url="https://ak/api/v3",
        admin_token="t",
        provider="authentik",
        identity_repo=identities,
        cache_ttl=30,
    )
    group_repo = OidcGroupRepository(
        oidc_url="https://ak/api/v3",
        admin_token="t",
        provider="authentik",
        identity_repo=identities,
    )
    person_svc = PersonService(person_repo=person_repo, group_repo=group_repo, uow=uow)

    entry_repo = SqlAlchemyAclEntryRepository(sessions)
    policy = AuthorizationPolicy(
        entry_repo=entry_repo,
        profile_provider=PersonProfileProvider(person_repo),
        hierarchy_provider=_NoHierarchy(),
        uow=uow,
    )
    return _OidcSystem(person_svc, person_repo, group_repo, policy, entry_repo, uow, idp)


# --------------------------------------------------------------------------
# 1) Gestione utenti via PersonService contro le admin API OIDC
# --------------------------------------------------------------------------

def test_person_crud_backed_by_idp(oidc_system: _OidcSystem):
    sys = oidc_system

    created = sys.person.add(["alice"])
    assert created.acl_level == ANON_SENTINEL  # profilo meno privilegiato alla nascita
    assert created.acl_groups == []
    assert len(sys.idp.users) == 1  # utente creato davvero sull'IdP (POST)

    fetched = sys.person.get(created.id)
    assert fetched.primary_nickname == "alice"

    listed = sys.person.list({})
    assert [p.primary_nickname for p in listed] == ["alice"]

    assert sys.person_repo.get_by_nickname("alice").nicknames == ["alice"]
    assert sys.person_repo.get_by_nickname("nessuno") is None

    sys.person.remove(created.id)
    assert sys.idp.users == {}  # DELETE propagata all'IdP


def test_group_crud_backed_by_idp(oidc_system: _OidcSystem):
    sys = oidc_system

    created = sys.person.add_group(name="ops")
    assert created.name == "ops"
    assert created.zone_type == "VIRTUAL"
    assert len(sys.idp.groups) == 1
    assert next(iter(sys.idp.groups.values()))["name"] == "ops"

    updated = sys.person.update_group(
        created.id,
        name="ops-nord",
        zone_type="GEOGRAPHIC",
        zone_description="nord",
    )
    assert updated.name == "ops-nord"
    assert updated.zone_type == "GEOGRAPHIC"
    assert updated.zone_description == "nord"

    stored = next(iter(sys.idp.groups.values()))["attributes"]
    assert next(iter(sys.idp.groups.values()))["name"] == "ops-nord"
    assert stored["zone_name"] == "ops-nord"
    assert stored["zone_type"] == "GEOGRAPHIC"
    assert stored["zone_description"] == "nord"

    reread = sys.person.get_group(created.id)
    assert reread.name == "ops-nord"
    assert [g.name for g in sys.person.list_groups()] == ["ops-nord"]

    sys.person.remove_group(created.id)
    assert sys.idp.groups == {}


def test_oidc_group_membership_round_trip(oidc_system: _OidcSystem):
    sys = oidc_system

    person = sys.person.add(["dave"])
    group = sys.person.add_group(name="squadra")

    sys.person.add_group_member(group.id, person.id)
    members = sys.person.list_by_group(group.id)
    assert [m.id for m in members] == [person.id]

    sys.person.remove_group_member(group.id, person.id)
    assert sys.person.list_by_group(group.id) == []


# --------------------------------------------------------------------------
# 2) set_acl_profile persiste il profilo ACL negli attributi utente dell'IdP
# --------------------------------------------------------------------------

def test_set_acl_profile_persists_to_idp(oidc_system: _OidcSystem):
    sys = oidc_system

    person = sys.person.add(["bob"])

    updated = sys.person.set_acl_profile(person.id, acl_level=50, acl_groups=["ops", "cmd"])
    assert updated.acl_level == 50
    assert updated.acl_groups == ["cmd", "ops"]

    # Persistito davvero sull'IdP (non solo nel DTO di ritorno):
    stored = next(iter(sys.idp.users.values()))["attributes"]
    assert stored["acl_level"] == 50
    assert set(stored["acl_groups"]) == {"ops", "cmd"}

    # E una rilettura indipendente lo riflette (cache invalidata dal save).
    reread = sys.person.get(person.id)
    assert reread.acl_level == 50
    assert set(reread.acl_groups) == {"ops", "cmd"}


# --------------------------------------------------------------------------
# 3) AuthorizationPolicy autorizza in base al profilo letto dall'IdP
# --------------------------------------------------------------------------

def test_authorization_uses_oidc_sourced_profile(oidc_system: _OidcSystem):
    sys = oidc_system

    # Entry di soglia: chiunque con livello <= 100 può VIEW su MISSION:*.
    threshold = AclEntry(
        id=uuid.uuid4(),
        subject=SubjectRef.public(),
        resource=ResourceRef.type_root(ResourceType.MISSION),
        operation=Operation.VIEW,
        permission=Permission.ALLOW,
        level=100,
    )
    threshold.validate()
    with sys.uow.transaction():
        sys.entry_repo.save(threshold)

    mission_root = ResourceRef.type_root(ResourceType.MISSION)
    alice = sys.person.add(["alice"])
    alice_id = uuid.UUID(alice.id)

    # Alla nascita il livello è ANON_SENTINEL (> 100): negato.
    assert sys.policy.is_allowed(alice_id, Operation.VIEW, mission_root) is False
    # Anche l'anonimo (principal None) è negato.
    assert sys.policy.is_allowed(None, Operation.VIEW, mission_root) is False

    # Promuovendo il profilo ACL sull'IdP (livello 50 <= 100) l'accesso è concesso.
    sys.person.set_acl_profile(alice.id, acl_level=50)
    assert sys.policy.is_allowed(alice_id, Operation.VIEW, mission_root) is True


# --------------------------------------------------------------------------
# 4) Paginazione: gli elenchi aggregano TUTTE le pagine (non solo la prima)
# --------------------------------------------------------------------------

def test_list_aggregates_all_authentik_pages(oidc_system: _OidcSystem):
    sys = oidc_system  # IdP finto con page_size=20

    for i in range(25):  # due pagine: 20 + 5
        sys.person.add([f"user{i:02d}"])
    assert sys.idp.calls["get"] == 0  # add() non fa GET

    listed = sys.person.list({})
    assert len(listed) == 25  # entrambe le pagine, non solo le prime 20
    assert sys.idp.calls["get"] == 2  # esattamente due pagine seguite


class _FakeIdentityRepo:
    def __init__(self):
        self._by_ext = {}

    def internal_id(self, provider, rtype, ext):
        key = (provider, rtype, str(ext))
        if key not in self._by_ext:
            self._by_ext[key] = uuid.uuid4()
        return self._by_ext[key]

    def external_id(self, provider, rtype, internal):
        return None


class _StatefulKeycloak:
    """Fake ``requests`` per Keycloak: elenco array paginato con first/max."""

    _MARKER = "/users/"

    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.get_calls = 0

    def get(self, url, params=None, headers=None, timeout=None, verify=True):
        self.get_calls += 1
        tail = url.split(self._MARKER, 1)[1].strip("/")
        if not tail:
            params = dict(params or {})
            first = int(params.pop("first", 0))
            page_max = int(params.pop("max", 100))
            rows = list(self.users.values())
            for key, value in params.items():
                rows = [r for r in rows if str(r.get(key)) == str(value)]
            return _Resp(rows[first : first + page_max], 200)
        rid = tail.split("/")[0]
        row = self.users.get(rid)
        return _Resp(row, 200) if row is not None else _Resp(None, 404)


def test_list_aggregates_all_keycloak_pages(monkeypatch):
    idp = _StatefulKeycloak()
    for i in range(250):  # tre pagine: 100 + 100 + 50 (max=100 di default)
        rid = f"kc-{i}"
        idp.users[rid] = {"id": rid, "username": f"user{i}", "attributes": {"acl_level": 100}}
    monkeypatch.setattr(pr_mod, "requests", idp)

    repo = OidcPersonRepository(
        oidc_url="https://kc/admin/realms/r",
        admin_token="t",
        provider="keycloak",
        identity_repo=_FakeIdentityRepo(),
    )

    persons = repo.list({})
    assert len(persons) == 250  # tutte le pagine aggregate via first/max
    assert idp.get_calls == 3  # 100 + 100 + 50: si ferma alla pagina corta


def test_authorization_uses_oidc_sourced_groups(oidc_system: _OidcSystem):
    sys = oidc_system

    # Entry per gruppo: solo chi è nel gruppo "ops" può EDIT su MISSION:*.
    entry = AclEntry(
        id=uuid.uuid4(),
        subject=SubjectRef.public(),
        resource=ResourceRef.type_root(ResourceType.MISSION),
        operation=Operation.EDIT,
        permission=Permission.ALLOW,
        level=100,
        group="ops",
        profile_join=JoinOp.AND,
    )
    entry.validate()
    with sys.uow.transaction():
        sys.entry_repo.save(entry)

    mission_root = ResourceRef.type_root(ResourceType.MISSION)
    carol = sys.person.add(["carol"])
    carol_id = uuid.UUID(carol.id)

    # Livello adeguato ma senza gruppo "ops": negato (profile_join AND).
    sys.person.set_acl_profile(carol.id, acl_level=10)
    assert sys.policy.is_allowed(carol_id, Operation.EDIT, mission_root) is False

    # Aggiunto il gruppo "ops" sull'IdP: concesso.
    sys.person.set_acl_profile(carol.id, acl_groups=["ops"])
    assert sys.policy.is_allowed(carol_id, Operation.EDIT, mission_root) is True
