# SPDX-License-Identifier: CC-BY-SA-4.0
"""Primo avvio: creazione dell'amministratore iniziale (locale e OIDC).

Copre:
  - backend persone locale compatibile con autenticazione OIDC;
  - dispatch di AuthService.admin_exists / create_initial_admin sul backend OIDC,
    con delega all'IdP e compensazione in caso di fallimento;
  - redirect del flusso Web /login → /setup finché manca un amministratore (locale).
"""
import asyncio
import types
from uuid import uuid4

import pytest

from src.config import SecurityConfigLoader
from src.application.services.auth_service import AuthService, INITIAL_ADMIN_ACL_LEVEL
from src.domain.acl import Profile
from src.domain.entities import Person
from src.domain.exceptions import AuthenticationError, ValidationError


# ---------------------------------------------------------------------------
# Configurazione: persone locali + login OIDC è supportato
# ---------------------------------------------------------------------------

def _load_with(monkeypatch, person_backend, auth_backend):
    monkeypatch.setenv("MISSIONMANAGER_PERSON_BACKEND", person_backend)
    monkeypatch.setenv("MISSIONMANAGER_AUTH_BACKEND", auth_backend)
    monkeypatch.setenv("MISSIONMANAGER_SECRET_KEY", "x" * 40)
    monkeypatch.delenv("MISSIONMANAGER_OIDC_ADMIN_TOKEN", raising=False)
    return SecurityConfigLoader.load()


def test_oidc_person_backend_requires_oidc_auth(monkeypatch):
    with pytest.raises(ValidationError, match="richiede auth_backend='oidc'"):
        _load_with(monkeypatch, "oidc", "local")


@pytest.mark.parametrize(
    "person_backend, auth_backend",
    [("local", "local"), ("local", "oidc"), ("oidc", "oidc")],
)
def test_supported_backend_combinations_are_accepted(monkeypatch, person_backend, auth_backend):
    cfg = _load_with(monkeypatch, person_backend, auth_backend)
    assert cfg.person_backend == person_backend
    assert cfg.auth_backend == auth_backend
    if (person_backend, auth_backend) == ("local", "oidc"):
        assert cfg.oidc_admin_token is None


def test_bootstrap_local_persons_oidc_auth_does_not_require_admin_token(monkeypatch, tmp_path):
    monkeypatch.delenv("MISSIONMANAGER_CONFIG_FILE", raising=False)
    monkeypatch.delenv("MISSIONMANAGER_OIDC_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("MISSIONMANAGER_DATABASE_URL", f"sqlite:///{tmp_path / 'mm.db'}")
    monkeypatch.setenv("MISSIONMANAGER_PERSON_BACKEND", "local")
    monkeypatch.setenv("MISSIONMANAGER_AUTH_BACKEND", "oidc")
    monkeypatch.setenv("MISSIONMANAGER_OIDC_ISSUER", "https://idp.example/realms/mm")
    monkeypatch.setenv("MISSIONMANAGER_OIDC_CLIENT_ID", "missionmanager")
    monkeypatch.setenv("MISSIONMANAGER_SECRET_KEY", "x" * 40)

    from src.bootstrap.common import build_system

    system = build_system()

    assert system.auth_service.admin_exists(system.person) is True


def test_oidc_auth_with_admin_params_selects_oidc_person_backend(monkeypatch):
    monkeypatch.delenv("MISSIONMANAGER_CONFIG_FILE", raising=False)
    monkeypatch.delenv("MISSIONMANAGER_PERSON_BACKEND", raising=False)
    monkeypatch.setenv("MISSIONMANAGER_AUTH_BACKEND", "oidc")
    monkeypatch.setenv("MISSIONMANAGER_OIDC_URL", "https://idp.example/api/v3")
    monkeypatch.setenv("MISSIONMANAGER_OIDC_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("MISSIONMANAGER_SECRET_KEY", "x" * 40)

    cfg = SecurityConfigLoader.load()

    assert cfg.auth_backend == "oidc"
    assert cfg.person_backend == "oidc"


def test_explicit_local_person_backend_wins_over_oidc_admin_params(monkeypatch):
    monkeypatch.delenv("MISSIONMANAGER_CONFIG_FILE", raising=False)
    monkeypatch.setenv("MISSIONMANAGER_PERSON_BACKEND", "local")
    monkeypatch.setenv("MISSIONMANAGER_AUTH_BACKEND", "oidc")
    monkeypatch.setenv("MISSIONMANAGER_OIDC_URL", "https://idp.example/api/v3")
    monkeypatch.setenv("MISSIONMANAGER_OIDC_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("MISSIONMANAGER_SECRET_KEY", "x" * 40)

    cfg = SecurityConfigLoader.load()

    assert cfg.auth_backend == "oidc"
    assert cfg.person_backend == "local"


def test_bootstrap_oidc_admin_params_wire_oidc_person_repository(monkeypatch, tmp_path):
    monkeypatch.delenv("MISSIONMANAGER_CONFIG_FILE", raising=False)
    monkeypatch.delenv("MISSIONMANAGER_PERSON_BACKEND", raising=False)
    monkeypatch.setenv("MISSIONMANAGER_DATABASE_URL", f"sqlite:///{tmp_path / 'mm.db'}")
    monkeypatch.setenv("MISSIONMANAGER_AUTH_BACKEND", "oidc")
    monkeypatch.setenv("MISSIONMANAGER_OIDC_URL", "https://idp.example/api/v3")
    monkeypatch.setenv("MISSIONMANAGER_OIDC_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("MISSIONMANAGER_OIDC_ISSUER", "https://idp.example/application/o/mm/")
    monkeypatch.setenv("MISSIONMANAGER_OIDC_CLIENT_ID", "missionmanager")
    monkeypatch.setenv("MISSIONMANAGER_SECRET_KEY", "x" * 40)

    from src.bootstrap.common import build_system
    from src.infrastructure.oidc.person_repository import OidcPersonRepository
    from src.infrastructure.oidc.group_repository import OidcGroupRepository

    system = build_system()

    assert isinstance(system.person_repo, OidcPersonRepository)
    assert isinstance(system.person._group_repo, OidcGroupRepository)


# ---------------------------------------------------------------------------
# AuthService: flusso di primo avvio OIDC (delega all'IdP)
# ---------------------------------------------------------------------------

class _FakeOidcPersonRepo:
    """Imita OidcPersonRepository per i soli metodi usati dal primo avvio."""

    def __init__(self, existing_levels=()):
        self._persons = {}  # id -> Person
        self.passwords = {}  # id -> password
        self.deleted = []
        self.fail_set_password = False
        self._existing_levels = list(existing_levels)

    # usato da admin_exists indirettamente via person_service.list
    def list(self, _filters):
        return [
            Person(id=uuid4(), nicknames=["x"], acl=Profile(level=lvl))
            for lvl in self._existing_levels
        ]

    def set_password(self, person_id, password):
        if self.fail_set_password:
            raise RuntimeError("IdP ha rifiutato la password")
        self.passwords[person_id] = password

    def delete(self, person_id):
        self.deleted.append(person_id)
        self._persons.pop(person_id, None)
        return True

    def get(self, person_id):
        return self._persons[person_id]

    # invocato dal fake person_service.add
    def save(self, person):
        self._persons[person.id] = person


class _FakePersonService:
    """person_service minimale: add()/set_acl_profile() sul repo, list() delegata."""

    def __init__(self, repo):
        self._repo = repo

    def add(self, nicknames):
        person = Person(id=uuid4(), nicknames=list(nicknames), acl=Profile())
        self._repo.save(person)
        return types.SimpleNamespace(id=str(person.id), acl_level=person.acl.level)

    def set_acl_profile(self, person_id, acl_level=None, acl_groups=None):
        from uuid import UUID
        person = self._repo.get(UUID(person_id))
        person.acl = Profile(
            level=acl_level if acl_level is not None else person.acl.level,
            groups=frozenset(acl_groups or person.acl.stored_groups()),
        )
        self._repo.save(person)
        return types.SimpleNamespace(id=str(person.id), acl_level=person.acl.level)

    def list(self, filters):
        persons = self._repo.list(filters)
        return [
            types.SimpleNamespace(id=str(p.id), acl_level=p.acl.level)
            for p in persons
        ]


def _oidc_auth_service(repo):
    # local_auth=None ⇒ backend OIDC; oidc_client non serve per questo flusso
    return AuthService(
        person_repo=repo,
        local_auth=None,
        oidc_client=object(),
        person_backend="oidc",
        auth_backend="oidc",
        uow=None,
    )


def test_oidc_admin_exists_requires_admin_level():
    # IdP con soli utenti non-admin (livelli alti = meno privilegiati)
    # ⇒ nessun amministratore presente
    repo = _FakeOidcPersonRepo(existing_levels=[100, 50, 20])
    svc = _FakePersonService(repo)
    auth = _oidc_auth_service(repo)
    assert auth.admin_exists(svc) is False

    # con un utente di livello <= soglia amministrativa, l'admin esiste
    repo2 = _FakeOidcPersonRepo(existing_levels=[100, INITIAL_ADMIN_ACL_LEVEL])
    auth2 = _oidc_auth_service(repo2)
    assert auth2.admin_exists(_FakePersonService(repo2)) is True


def test_oidc_create_initial_admin_delegates_to_idp():
    repo = _FakeOidcPersonRepo(existing_levels=[1])
    svc = _FakePersonService(repo)
    auth = _oidc_auth_service(repo)

    person = auth.create_initial_admin(svc, "admin", "ValidPassword1!")

    assert person.acl.level == INITIAL_ADMIN_ACL_LEVEL
    assert repo.passwords[person.id] == "ValidPassword1!"
    assert repo.deleted == []


def test_oidc_create_initial_admin_rejects_short_password_without_creating():
    repo = _FakeOidcPersonRepo()
    svc = _FakePersonService(repo)
    auth = _oidc_auth_service(repo)

    with pytest.raises(ValidationError):
        auth.create_initial_admin(svc, "admin", "short")

    # nessun utente creato nell'IdP: la validazione precede la POST
    assert repo._persons == {}
    assert repo.passwords == {}


def test_oidc_create_initial_admin_compensates_on_password_failure():
    repo = _FakeOidcPersonRepo()
    repo.fail_set_password = True
    svc = _FakePersonService(repo)
    auth = _oidc_auth_service(repo)

    with pytest.raises(RuntimeError):
        auth.create_initial_admin(svc, "admin", "ValidPassword1!")

    # l'utente appena creato nell'IdP è stato rimosso per compensazione
    assert len(repo.deleted) == 1
    assert repo._persons == {}


# ---------------------------------------------------------------------------
# Web: /login dirotta su /setup finché manca un amministratore (backend locale)
# ---------------------------------------------------------------------------

def test_web_login_redirects_to_setup_until_admin_exists(web_app, seed_admin):
    app, svcs = web_app

    async def scenario():
        client = app.test_client()
        # nessun admin ⇒ /login redirige a /setup
        r = await client.get("/login")
        assert r.status_code in (302, 303)
        assert "/setup" in r.headers["Location"]

        # creato l'admin ⇒ /setup redirige al login
        seed_admin(svcs)
        r = await client.get("/setup")
        assert r.status_code in (302, 303)
        assert "/login" in r.headers["Location"]

    asyncio.run(scenario())
