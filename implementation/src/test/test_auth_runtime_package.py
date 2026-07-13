# SPDX-License-Identifier: CC-BY-SA-4.0
"""Regressioni sul package runtime ``auth`` standalone.

Questi test coprono il nucleo framework-neutral usato dai frontend runtime:
sessioni, token, request gateway e protezioni di sicurezza.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from auth.application.authentication_service import AuthenticationService
from auth.application.dtos import AuthContext, RequestOutcomeKind
from auth.application.request_gateway import RequestGateway
from auth.application.session_service import SessionService
from auth.application.token_service import TokenService
from auth.domain.access_control import ResourceRef, SubjectRef
from auth.domain.account import Account, AccountKind, AccountStatus
from auth.domain.credentials import LocalCredential
from auth.domain.errors import AuthenticationError, AuthorizationDenied
from auth.domain.identity import AuthMethod, RequestIdentity
from auth.domain.profile import AuthorizationProfile
from auth.domain.request import (
    AuthRequest,
    CredentialKind,
    CredentialMode,
    CredentialPresentation,
    ProtectionRequirements,
    RequestOrigin,
)
from auth.domain.types import AccountId, ProfileId
from auth.infrastructure.memory.repositories import InMemoryAuthRepository
from auth.infrastructure.security.clock import FrozenClock
from auth.infrastructure.security.password import Pbkdf2PasswordHasher
from auth.infrastructure.security.protections import (
    HmacAntiForgeryProtector,
    ReturnTargetRedirectValidator,
)
from auth.infrastructure.security.rate_limit import InMemoryRateLimitPolicy
from auth.infrastructure.security.token import HmacTokenSigner


NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


class _DeterministicRandom:
    def __init__(self) -> None:
        self._counter = 0

    def token_urlsafe(self, nbytes: int = 32) -> str:
        self._counter += 1
        return f"token-{nbytes}-{self._counter}"

    def uuid4_hex(self) -> str:
        self._counter += 1
        return f"{self._counter:032x}"


class _IdentityResolver:
    def __init__(self, identity: RequestIdentity) -> None:
        self._identity = identity

    def resolve(self, request: AuthRequest) -> RequestIdentity:
        return self._identity


class _Authorization:
    def __init__(self, *, denied: bool = False) -> None:
        self.denied = denied
        self.calls: list[tuple[RequestIdentity, str, ResourceRef]] = []

    def require(self, identity: RequestIdentity, operation: str, resource: ResourceRef) -> None:
        self.calls.append((identity, operation, resource))
        if self.denied:
            raise AuthorizationDenied("denied")


def _account(account_id: str = "alice", *, version: int = 0) -> Account:
    return Account(
        id=AccountId(account_id),
        username=account_id,
        email=f"{account_id}@example.test",
        kind=AccountKind.HUMAN,
        status=AccountStatus.ACTIVE,
        profile_id=ProfileId("profile-admin"),
        authz_version=version,
        flags=frozenset(),
        created_at=NOW,
        updated_at=NOW,
    )


def _repo_with_account(account: Account | None = None) -> InMemoryAuthRepository:
    repo = InMemoryAuthRepository()
    repo.save(AuthorizationProfile(ProfileId("profile-admin"), level=0, groups=frozenset({"admins"}), version=0))
    repo.save(account or _account())
    return repo


def _token_service(repo: InMemoryAuthRepository, clock: FrozenClock) -> TokenService:
    return TokenService(
        accounts=repo,
        tokens=repo,
        revocations=repo,
        signer=HmacTokenSigner("runtime-secret"),
        clock=clock,
        random=_DeterministicRandom(),
        issuer="missionmanager",
        audience="runtime",
        access_ttl=timedelta(minutes=5),
        refresh_ttl=timedelta(hours=1),
    )


def test_token_service_rejects_stale_and_revoked_access_tokens():
    clock = FrozenClock(NOW)
    repo = _repo_with_account()
    service = _token_service(repo, clock)

    first = service.issue_access_token(repo.accounts[AccountId("alice")], AuthContext(issue_session=False))
    principal = service.verify_access_token(first.value)
    assert principal.account_id == AccountId("alice")
    assert principal.authz_version == 0

    repo.save(repo.accounts[AccountId("alice")].with_profile(ProfileId("profile-other"), NOW + timedelta(seconds=1)))
    with pytest.raises(AuthenticationError):
        service.verify_access_token(first.value)

    second = service.issue_access_token(repo.accounts[AccountId("alice")], AuthContext(issue_session=False))
    service.revoke_access_token(second.value)
    with pytest.raises(AuthenticationError):
        service.verify_access_token(second.value)


def test_refresh_token_rotation_revokes_the_old_refresh_record():
    clock = FrozenClock(NOW)
    repo = _repo_with_account()
    service = _token_service(repo, clock)

    refresh = service.issue_refresh_token(repo.accounts[AccountId("alice")])
    pair = service.rotate_refresh_token(refresh.value)

    assert pair.access_token.value
    assert pair.refresh_token is not None
    with pytest.raises(AuthenticationError):
        service.rotate_refresh_token(refresh.value)
    assert len(repo.list_refresh_family(refresh.family_id)) == 2


def test_session_service_touches_sessions_and_fails_closed_on_authz_version_change():
    clock = FrozenClock(NOW)
    repo = _repo_with_account()
    service = SessionService(repo, repo, clock, _DeterministicRandom(), max_age=timedelta(minutes=30))

    session = service.create_session(AccountId("alice"), AuthContext(origin="web"), auth_method=AuthMethod.LOCAL_PASSWORD)
    clock.set(NOW + timedelta(minutes=5))
    touched = service.get_session(session.id)

    assert touched is not None
    assert touched.last_seen_at == clock.now()

    repo.save(repo.accounts[AccountId("alice")].with_profile(ProfileId("profile-other"), NOW + timedelta(minutes=6)))
    assert service.get_session(session.id) is None


def test_authentication_service_issues_session_tokens_and_enforces_lockout():
    clock = FrozenClock(NOW)
    repo = _repo_with_account()
    hasher = Pbkdf2PasswordHasher(iterations=2, salt_bytes=4)
    repo.save(
        LocalCredential(
            account_id=AccountId("alice"),
            password_hash=hasher.hash("ValidPassword1!"),
            hash_algorithm=hasher.algorithm,
            hash_version=hasher.version,
            failed_attempts=0,
            locked_until=None,
            password_changed_at=NOW,
            must_change=False,
        )
    )
    sessions = SessionService(repo, repo, clock, _DeterministicRandom())
    tokens = _token_service(repo, clock)
    service = AuthenticationService(
        "local",
        accounts=repo,
        credentials=repo,
        password_hasher=hasher,
        clock=clock,
        sessions=sessions,
        tokens=tokens,
        max_failed_attempts=2,
        lockout_duration=timedelta(minutes=10),
    )

    result = service.login_local(
        " Alice ",
        "ValidPassword1!",
        AuthContext(issue_session=True, issue_tokens=True, issue_refresh_token=True, return_target="/after-login"),
    )

    assert result.session is not None
    assert result.access_token is not None
    assert result.refresh_token is not None
    assert result.return_target == "/after-login"

    with pytest.raises(AuthenticationError):
        service.login_local("alice", "wrong")
    with pytest.raises(AuthenticationError):
        service.login_local("alice", "wrong")
    with pytest.raises(AuthenticationError):
        service.login_local("alice", "ValidPassword1!")


def _request(
    *,
    credentials: tuple[CredentialPresentation, ...],
    mutation: bool = False,
    return_target: str | None = "/ok",
) -> AuthRequest:
    return AuthRequest(
        id="req-1",
        origin=RequestOrigin("web", "http", trusted=True, address="127.0.0.1"),
        credential_presentations=credentials,
        operation="VIEW",
        resource=ResourceRef("MISSION", "m1"),
        mutation=mutation,
        protection=ProtectionRequirements(
            allow_anonymous=False,
            require_active_account=False,
            require_return_target=True,
        ),
        return_target=return_target,
    )


def test_request_gateway_validates_redirect_csrf_rate_limit_and_authorization():
    identity = RequestIdentity(
        subject=SubjectRef.user(AccountId("alice")),
        account_id=AccountId("alice"),
        auth_method=AuthMethod.SESSION,
        authenticated_at=NOW,
    )
    authorization = _Authorization()
    anti_forgery = HmacAntiForgeryProtector("csrf-secret")
    gateway = RequestGateway(
        _IdentityResolver(identity),
        authorization,  # type: ignore[arg-type]
        rate_limit_policy=InMemoryRateLimitPolicy(max_requests=1, window=timedelta(minutes=1)),
        anti_forgery=anti_forgery,
        redirect_validator=ReturnTargetRedirectValidator(),
    )
    credentials = (
        CredentialPresentation(CredentialKind.SESSION_ID, CredentialMode.AMBIENT, "sid"),
        CredentialPresentation(
            CredentialKind.NONE,
            CredentialMode.EXPLICIT,
            anti_forgery.issue("sid"),
            issuer="anti_forgery",
        ),
    )

    allowed = gateway.handle(_request(credentials=credentials, mutation=True))
    assert allowed.kind is RequestOutcomeKind.ALLOWED
    assert authorization.calls[-1][1:] == ("VIEW", ResourceRef("MISSION", "m1"))

    limited = gateway.handle(_request(credentials=credentials, mutation=True))
    assert limited.kind is RequestOutcomeKind.RATE_LIMITED
    assert limited.retry_after_seconds is not None


def test_request_gateway_fails_closed_for_missing_csrf_invalid_redirect_and_denial():
    identity = RequestIdentity(
        subject=SubjectRef.user(AccountId("alice")),
        account_id=AccountId("alice"),
        auth_method=AuthMethod.SESSION,
        authenticated_at=NOW,
    )
    session_only = (CredentialPresentation(CredentialKind.SESSION_ID, CredentialMode.AMBIENT, "sid"),)

    missing_csrf = RequestGateway(
        _IdentityResolver(identity),
        _Authorization(),  # type: ignore[arg-type]
        anti_forgery=HmacAntiForgeryProtector("csrf-secret"),
        redirect_validator=ReturnTargetRedirectValidator(),
    ).handle(_request(credentials=session_only, mutation=True))
    assert missing_csrf.kind is RequestOutcomeKind.FORGERY_PROTECTION_FAILED

    bad_redirect = RequestGateway(
        _IdentityResolver(identity),
        _Authorization(),  # type: ignore[arg-type]
        redirect_validator=ReturnTargetRedirectValidator(),
    ).handle(_request(credentials=session_only, return_target="https://evil.example/"))
    assert bad_redirect.kind is RequestOutcomeKind.INVALID_REQUEST

    denied = RequestGateway(
        _IdentityResolver(identity),
        _Authorization(denied=True),  # type: ignore[arg-type]
        redirect_validator=ReturnTargetRedirectValidator(),
    ).handle(_request(credentials=session_only))
    assert denied.kind is RequestOutcomeKind.AUTHORIZATION_DENIED


def test_password_hasher_and_anti_forgery_helpers_are_fail_closed():
    hasher = Pbkdf2PasswordHasher(iterations=2, salt_bytes=4)
    stored = hasher.hash("ValidPassword1!")
    assert hasher.verify("ValidPassword1!", stored) is True
    assert hasher.verify("wrong", stored) is False
    assert hasher.needs_rehash(stored) is False
    assert Pbkdf2PasswordHasher(iterations=3, salt_bytes=4).needs_rehash(stored) is True

    protector = HmacAntiForgeryProtector("csrf-secret")
    token = protector.issue("session-secret")
    assert protector.verify_token(token) is True
    assert protector.verify_token(token + "tampered") is False

    redirect = ReturnTargetRedirectValidator()
    assert redirect.sanitize("/local?x=1") == "/local?x=1"
    assert redirect.sanitize("//evil.example") == "/"
    assert redirect.sanitize("https://evil.example") == "/"
