# SPDX-License-Identifier: CC-BY-SA-4.0
"""Verifiche dei flussi OIDC dopo gli interventi P1–P5.

Niente rete reale: il modulo `requests` usato da OidcPersonRepository è
sostituito con un fake, e l'ExternalIdentityRepository con uno in-memory che
replica la semantica (internal_id crea il binding se assente).
"""
import uuid

import pytest

from src.application.services.auth_service import AuthService
from src.bootstrap.rest import _validate_rest_oidc_config
from src.config import SecurityConfig
from src.domain.acl import Profile
from src.domain.exceptions import AuthenticationError
from src.domain.entities import Person
from src.infrastructure.auth.oidc_client import OidcTokenSet
from src.infrastructure.identity.rest import RestOperatorIdentityAdapter
from src.infrastructure.oidc import group_repository as gr_mod
from src.infrastructure.oidc import person_repository as pr_mod
from src.infrastructure.oidc.group_repository import OidcGroupRepository
from src.infrastructure.oidc.local_person_repository import LocalOidcPersonRepository
from src.infrastructure.oidc.person_repository import OidcPersonRepository
from src.infrastructure.repositories.external_identity_repository import (
    SqlAlchemyExternalIdentityRepository,
)
from src.infrastructure.repositories.person_repository import SqlAlchemyPersonRepository


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class _Resp:
    def __init__(self, json_data=None, status_code=200, headers=None):
        self._json = json_data
        self.status_code = status_code
        self.headers = headers or {}
        self.text = ""
        self.ok = 200 <= status_code < 300

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeRequests:
    def __init__(self):
        self.calls = {"get": 0, "post": 0, "patch": 0, "delete": 0, "put": 0}
        self.last = {}
        self.get_response = _Resp({})
        self.patch_response = _Resp({}, 200)
        self.delete_response = _Resp({}, 204)
        self.post_response = _Resp({"pk": 5}, 201)
        self.put_response = _Resp({}, 200)

    def get(self, *a, **k):
        self.calls["get"] += 1
        self.last["get"] = (a, k)
        return self.get_response

    def post(self, *a, **k):
        self.calls["post"] += 1
        self.last["post"] = (a, k)
        return self.post_response

    def patch(self, *a, **k):
        self.calls["patch"] += 1
        self.last["patch"] = (a, k)
        return self.patch_response

    def delete(self, *a, **k):
        self.calls["delete"] += 1
        self.last["delete"] = (a, k)
        return self.delete_response

    def put(self, *a, **k):
        self.calls["put"] += 1
        self.last["put"] = (a, k)
        return self.put_response


class _FakeIdentityRepo:
    def __init__(self):
        self._by_ext = {}
        self._by_int = {}

    def internal_id(self, provider, rtype, ext):
        key = (provider, rtype, str(ext))
        if key in self._by_ext:
            return self._by_ext[key]
        iid = uuid.uuid4()
        self.bind(provider, rtype, str(ext), iid)
        return iid

    def external_id(self, provider, rtype, internal):
        return self._by_int.get((provider, rtype, internal))

    def bind(self, provider, rtype, ext, internal):
        self._by_ext[(provider, rtype, str(ext))] = internal
        self._by_int[(provider, rtype, internal)] = str(ext)

    def delete(self, provider, rtype, internal):
        ext = self._by_int.pop((provider, rtype, internal), None)
        if ext is not None:
            self._by_ext.pop((provider, rtype, ext), None)


@pytest.fixture
def fake_requests(monkeypatch):
    fake = _FakeRequests()
    monkeypatch.setattr(pr_mod, "requests", fake)
    monkeypatch.setattr(gr_mod, "requests", fake)
    return fake


# --------------------------------------------------------------------------
# P1 — resolve_external_subject: traduzione sub → path-id
# --------------------------------------------------------------------------

def test_resolve_subject_without_field_uses_sub_directly(fake_requests):
    ids = _FakeIdentityRepo()
    repo = OidcPersonRepository(
        oidc_url="https://kc/admin/realms/r",
        admin_token="t",
        provider="keycloak",
        identity_repo=ids,
        subject_field=None,
    )
    internal = repo.resolve_external_subject("kc-user-id")
    # nessun lookup HTTP: sub == id admin
    assert fake_requests.calls["get"] == 0
    # coerente con le letture, che chiavano sul path-id ("id" per Keycloak)
    assert internal == ids.internal_id("keycloak", "person", "kc-user-id")


def test_resolve_subject_translates_via_lookup_authentik(fake_requests):
    ids = _FakeIdentityRepo()
    fake_requests.get_response = _Resp(
        {"results": [{"pk": 5, "uuid": "sub-uuid", "username": "bob"}]}
    )
    repo = OidcPersonRepository(
        oidc_url="https://ak/api/v3",
        admin_token="t",
        provider="authentik",
        identity_repo=ids,
        subject_field="uuid",
    )
    internal = repo.resolve_external_subject("sub-uuid")
    assert fake_requests.calls["get"] == 1
    # il binding è chiavato sul path-id (pk=5), coerente con _row_to_person/list
    assert internal == ids.internal_id("authentik", "person", "5")


def test_resolve_subject_raises_when_no_user_matches(fake_requests):
    ids = _FakeIdentityRepo()
    fake_requests.get_response = _Resp({"results": []})
    repo = OidcPersonRepository(
        oidc_url="https://ak/api/v3",
        admin_token="t",
        provider="authentik",
        identity_repo=ids,
        subject_field="uuid",
    )
    with pytest.raises(AuthenticationError):
        repo.resolve_external_subject("sconosciuto")


def test_resolve_subject_wraps_provider_bad_request(fake_requests):
    ids = _FakeIdentityRepo()
    fake_requests.get_response = _Resp({"detail": "bad request"}, status_code=400)
    repo = OidcPersonRepository(
        oidc_url="https://ak/api/v3",
        admin_token="t",
        provider="authentik",
        identity_repo=ids,
        subject_field="uuid",
    )

    with pytest.raises(AuthenticationError, match="Subject OIDC non risolvibile"):
        repo.resolve_external_subject("e8a08d4f8a2eb31713f84cd05dac2ccc")


# --------------------------------------------------------------------------
# P4 — cache a TTL breve su get()
# --------------------------------------------------------------------------

def _authentik_repo(ids, fake_requests, cache_ttl=30):
    fake_requests.get_response = _Resp(
        {"pk": 5, "username": "bob", "attributes": {"acl_level": 10}}
    )
    repo = OidcPersonRepository(
        oidc_url="https://ak/api/v3",
        admin_token="t",
        provider="authentik",
        identity_repo=ids,
        cache_ttl=cache_ttl,
    )
    pid = ids.internal_id("authentik", "person", "5")
    return repo, pid


def test_get_is_cached_within_ttl(fake_requests):
    ids = _FakeIdentityRepo()
    repo, pid = _authentik_repo(ids, fake_requests)
    p1 = repo.get(pid)
    p2 = repo.get(pid)
    assert p1.acl.level == 10 and p2.acl.level == 10
    assert fake_requests.calls["get"] == 1  # secondo get servito dalla cache


def test_cache_invalidated_on_save(fake_requests):
    ids = _FakeIdentityRepo()
    repo, pid = _authentik_repo(ids, fake_requests)
    repo.get(pid)
    repo.save(Person(id=pid, nicknames=["bob"], acl=Profile(level=10)))
    repo.get(pid)
    assert fake_requests.calls["patch"] == 1
    assert fake_requests.calls["get"] == 2  # cache invalidata → nuova lettura


def test_cache_disabled_when_ttl_not_positive(fake_requests):
    ids = _FakeIdentityRepo()
    repo, pid = _authentik_repo(ids, fake_requests, cache_ttl=0)
    repo.get(pid)
    repo.get(pid)
    assert fake_requests.calls["get"] == 2


# --------------------------------------------------------------------------
# P4 — ACL dai claim del token JWT (REST)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "claims, expected_level, expected_groups",
    [
        ({"acl_level": 7}, 7, set()),
        ({"acl_level": 5, "acl_groups": ["ops"]}, 5, {"ops"}),
        ({"acl_level": 5, "acl_groups": "ops, cmd"}, 5, {"ops", "cmd"}),
    ],
)
def test_acl_from_claims_present(claims, expected_level, expected_groups):
    profile = RestOperatorIdentityAdapter._acl_from_claims(claims)
    assert profile is not None
    assert profile.level == expected_level
    # "public" è il gruppo universale implicito, sempre presente
    assert profile.groups == expected_groups | {"public"}


@pytest.mark.parametrize(
    "claims",
    [{}, {"acl_groups": ["cmd"]}, {"acl_level": -1}, {"acl_level": "x"}],
)
def test_acl_from_claims_absent_or_invalid_returns_none(claims):
    assert RestOperatorIdentityAdapter._acl_from_claims(claims) is None


# --------------------------------------------------------------------------
# P3 — validazione bootstrap REST OIDC
# --------------------------------------------------------------------------

def test_rest_oidc_requires_jwks_and_audience():
    cfg = SecurityConfig(auth_backend="oidc", oidc_jwks_url=None, oidc_audience=None)
    with pytest.raises(RuntimeError, match="oidc_jwks_url"):
        _validate_rest_oidc_config(cfg)


def test_rest_oidc_ok_when_jwks_and_audience_set():
    cfg = SecurityConfig(auth_backend="oidc", oidc_jwks_url="https://idp/jwks", oidc_audience="mm")
    _validate_rest_oidc_config(cfg)  # non solleva


def test_rest_local_skips_oidc_validation():
    _validate_rest_oidc_config(SecurityConfig(auth_backend="local"))  # non solleva


# --------------------------------------------------------------------------
# P2 — flusso OIDC stateless
# --------------------------------------------------------------------------

class _FakeOidcClient:
    def __init__(self, claims=None):
        self.claims = claims or {"sub": str(uuid.uuid4()), "preferred_username": "oidc-user"}
        self.auth_kwargs = None
        self.logout_kwargs = None

    def build_auth_url(self, **kwargs):
        self.auth_kwargs = kwargs
        return "https://idp/authorize?x=1"

    def build_logout_url(self, **kwargs):
        self.logout_kwargs = kwargs
        return "https://idp/logout?x=1"

    def exchange_code(self, code, redirect_uri, code_verifier):
        return OidcTokenSet(access_token="access", id_token="id", refresh_token=None)

    def validate_id_token(self, id_token, nonce):
        return dict(self.claims)


def test_begin_oidc_flow_returns_stateless_params():
    auth = AuthService(person_repo=None, oidc_client=_FakeOidcClient())
    flow = auth.begin_oidc_flow("https://app/callback")
    assert set(flow) == {"url", "state", "nonce", "code_verifier"}
    assert flow["state"] and flow["nonce"] and flow["code_verifier"]


def test_begin_oidc_flow_can_force_login_prompt():
    client = _FakeOidcClient()
    auth = AuthService(person_repo=None, oidc_client=client)

    auth.begin_oidc_flow("https://app/callback", prompt="login")

    assert client.auth_kwargs["prompt"] == "login"


def test_build_oidc_logout_url_delegates_to_client():
    client = _FakeOidcClient()
    auth = AuthService(person_repo=None, oidc_client=client)

    url = auth.build_oidc_logout_url(
        post_logout_redirect_uri="https://app/login",
        id_token_hint="id-token",
    )

    assert url == "https://idp/logout?x=1"
    assert client.logout_kwargs == {
        "post_logout_redirect_uri": "https://app/login",
        "id_token_hint": "id-token",
    }


def _local_oidc_auth_service(session, claims):
    person_repo = LocalOidcPersonRepository(
        SqlAlchemyPersonRepository(session),
        SqlAlchemyExternalIdentityRepository(session),
        provider="authentik",
    )
    auth = AuthService(
        person_repo=person_repo,
        oidc_client=_FakeOidcClient(claims),
        person_backend="local",
        auth_backend="oidc",
        oidc_auto_provision_local=True,
    )
    return auth, person_repo


def test_complete_oidc_flow_auto_provisions_local_users_without_admin_token(fk_session):
    auth, person_repo = _local_oidc_auth_service(
        fk_session,
        {"sub": "sub-1", "preferred_username": "alice"},
    )

    first, token_set = auth.complete_oidc_flow(
        code="c", state="s", nonce="n", code_verifier="v"
    )

    assert token_set.access_token == "access"
    assert first.primary_nickname() == "alice"
    assert first.acl.level == 0
    assert person_repo.resolve_external_subject("sub-1") == first.id

    auth2, _ = _local_oidc_auth_service(
        fk_session,
        {"sub": "sub-2", "preferred_username": "bob"},
    )
    second, _ = auth2.complete_oidc_flow(
        code="c", state="s", nonce="n", code_verifier="v"
    )

    assert second.primary_nickname() == "bob"
    assert second.acl.level == Profile().level
    assert person_repo.resolve_external_subject("sub-2") == second.id


# --------------------------------------------------------------------------
# Group membership OIDC — Web App usa add/remove membri anche con backend OIDC
# --------------------------------------------------------------------------

def test_authentik_group_membership_uses_add_remove_user_endpoints(fake_requests):
    ids = _FakeIdentityRepo()
    group_id = uuid.uuid4()
    person_id = uuid.uuid4()
    ids.bind("authentik", "group", "group-uuid", group_id)
    ids.bind("authentik", "person", "5", person_id)
    fake_requests.post_response = _Resp({}, 204)
    repo = OidcGroupRepository(
        oidc_url="https://ak/api/v3",
        admin_token="t",
        provider="authentik",
        identity_repo=ids,
    )

    repo.add_member(group_id, person_id)
    args, kwargs = fake_requests.last["post"]
    assert args[0].endswith("/core/groups/group-uuid/add_user/")
    assert kwargs["json"] == {"pk": 5}

    repo.remove_member(group_id, person_id)
    args, kwargs = fake_requests.last["post"]
    assert args[0].endswith("/core/groups/group-uuid/remove_user/")
    assert kwargs["json"] == {"pk": 5}


def test_keycloak_group_membership_uses_user_group_endpoints(fake_requests):
    ids = _FakeIdentityRepo()
    group_id = uuid.uuid4()
    person_id = uuid.uuid4()
    ids.bind("keycloak", "group", "group-id", group_id)
    ids.bind("keycloak", "person", "user-id", person_id)
    repo = OidcGroupRepository(
        oidc_url="https://kc/admin/realms/r",
        admin_token="t",
        provider="keycloak",
        identity_repo=ids,
    )

    repo.add_member(group_id, person_id)
    args, _ = fake_requests.last["put"]
    assert args[0].endswith("/users/user-id/groups/group-id")

    repo.remove_member(group_id, person_id)
    args, _ = fake_requests.last["delete"]
    assert args[0].endswith("/users/user-id/groups/group-id")


def test_complete_oidc_flow_requires_nonce_and_verifier():
    auth = AuthService(person_repo=None, oidc_client=_FakeOidcClient())
    with pytest.raises(AuthenticationError):
        auth.complete_oidc_flow(code="c", state="s", nonce="", code_verifier="")
