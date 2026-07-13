# SPDX-License-Identifier: CC-BY-SA-4.0
"""Local authentication adapter backed by the external ``auth`` package."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

from auth.application.authentication_service import AuthenticationService as CoreAuthenticationService
from auth.application.dtos import AuthContext
from auth.application.token_service import TokenService
from auth.domain.account import Account, AccountKind, AccountStatus
from auth.domain.credentials import LocalCredential as CoreLocalCredential
from auth.domain.errors import AuthError, AuthenticationError as CoreAuthenticationError
from auth.domain.errors import ValidationError as CoreValidationError
from auth.domain.policies import PasswordPolicy as CorePasswordPolicy
from auth.domain.types import AccountId, ProfileId
from auth.infrastructure.security.clock import SystemClock
from auth.infrastructure.security.password import BcryptPasswordHasher
from auth.infrastructure.security.random import SecretsSecureRandom
from auth.infrastructure.security.token import HmacTokenSigner

from ...domain.auth import CredentialRepository, LocalCredential
from ...domain.entities import Person
from ...domain.exceptions import AuthenticationError, ValidationError
from ...domain.repositories import PersonRepository

_LOCAL_ISSUER = "missionmanager"
_AUDIENCE = "missionmanager"


@dataclass(frozen=True)
class PasswordPolicy:
    min_length: int = 12
    require_uppercase: bool = True
    require_digit: bool = True
    require_special: bool = True

    def to_core(self) -> CorePasswordPolicy:
        return CorePasswordPolicy(
            min_length=self.min_length,
            require_uppercase=self.require_uppercase,
            require_digit=self.require_digit,
            require_special=self.require_special,
        )

    def validate(self, password: str) -> None:
        try:
            self.to_core().validate(password)
            BcryptPasswordHasher().hash(password)
        except CoreValidationError as exc:
            raise ValidationError(str(exc), field="password") from exc


class _PersonAccountRepository:
    def __init__(self, person_repo: PersonRepository, uow=None) -> None:
        self._persons = person_repo
        self._uow = uow

    def get_by_id(self, account_id: AccountId) -> Account | None:
        return self._person_to_account(self._get_person(str(account_id)))

    def get_by_username(self, username: str) -> Account | None:
        normalized = username.strip().casefold()
        with self._txn():
            for person in self._persons.list({}):
                if any(nick.strip().casefold() == normalized for nick in person.nicknames):
                    return self._person_to_account(person)
        return None

    def get_by_email(self, email: str) -> Account | None:
        return self.get_by_username(email)

    def exists_active(self) -> bool:
        with self._txn():
            return bool(self._persons.list({}))

    def _get_person(self, raw_id: str) -> Person | None:
        try:
            person_id = UUID(raw_id)
        except ValueError:
            return None
        try:
            with self._txn():
                return self._persons.get(person_id)
        except Exception:
            return None

    def _txn(self):
        return self._uow.transaction() if self._uow is not None else nullcontext()

    @staticmethod
    def _person_to_account(person: Person | None) -> Account | None:
        if person is None:
            return None
        now = datetime.now(timezone.utc)
        username = person.primary_nickname().strip().casefold()
        if not username:
            username = str(person.id)
        return Account(
            id=AccountId(str(person.id)),
            username=username,
            email=None,
            kind=AccountKind.HUMAN,
            status=AccountStatus.ACTIVE,
            profile_id=ProfileId(str(person.id)),
            authz_version=0,
            flags=frozenset(),
            created_at=now,
            updated_at=now,
        )


class _CredentialRepositoryAdapter:
    def __init__(self, credentials: CredentialRepository, uow=None) -> None:
        self._credentials = credentials
        self._uow = uow

    def get(self, account_id: AccountId) -> CoreLocalCredential | None:
        credential = self._get_local(account_id)
        return self._to_core(credential) if credential is not None else None

    def save(self, credential: CoreLocalCredential) -> None:
        self._save_local(self._from_core(credential))

    def delete(self, account_id: AccountId) -> None:
        with self._txn():
            self._credentials.delete(UUID(str(account_id)))

    def record_failure(
        self,
        account_id: AccountId,
        *,
        now: datetime,
        max_attempts: int,
        lockout_duration: timedelta,
    ) -> CoreLocalCredential | None:
        with self._txn():
            current = self._credentials.get(UUID(str(account_id)))
            if current is None:
                return None
            current.failed_attempts += 1
            if max_attempts > 0 and current.failed_attempts >= max_attempts:
                current.locked_until = now + lockout_duration
            self._credentials.save(current)
            return self._to_core(current)

    def reset_failures(self, account_id: AccountId) -> CoreLocalCredential | None:
        with self._txn():
            current = self._credentials.get(UUID(str(account_id)))
            if current is None:
                return None
            current.failed_attempts = 0
            current.locked_until = None
            self._credentials.save(current)
            return self._to_core(current)

    def _get_local(self, account_id: AccountId) -> LocalCredential | None:
        with self._txn():
            return self._credentials.get(UUID(str(account_id)))

    def _save_local(self, credential: LocalCredential) -> None:
        with self._txn():
            self._credentials.save(credential)

    def _txn(self):
        return self._uow.transaction() if self._uow is not None else nullcontext()

    @staticmethod
    def _to_core(credential: LocalCredential) -> CoreLocalCredential:
        changed_at = datetime.now(timezone.utc)
        locked_until = credential.locked_until
        if locked_until is not None and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        return CoreLocalCredential(
            account_id=AccountId(str(credential.person_id)),
            password_hash=credential.hashed_password,
            hash_algorithm="bcrypt",
            hash_version=1,
            failed_attempts=credential.failed_attempts,
            locked_until=locked_until,
            password_changed_at=changed_at,
            must_change=credential.must_change_password,
        )

    @staticmethod
    def _from_core(credential: CoreLocalCredential) -> LocalCredential:
        return LocalCredential(
            person_id=UUID(str(credential.account_id)),
            hashed_password=credential.password_hash,
            failed_attempts=credential.failed_attempts,
            locked_until=credential.locked_until,
            must_change_password=credential.must_change,
        )


class _TokenRepository:
    def save_refresh_token(self, record) -> None:
        return None

    def get_refresh_token_by_hash(self, token_hash: str):
        return None

    def get_refresh_token(self, token_id):
        return None

    def list_refresh_family(self, family_id) -> list:
        return []

    def save_refresh_family(self, records: list) -> None:
        return None


class _TokenRevocationAdapter:
    def __init__(self, delegate=None) -> None:
        self._delegate = delegate
        self._revoked: dict[str, datetime] = {}

    def revoke(self, jti: str, ttl_seconds: int | datetime) -> None:
        if self._delegate is not None:
            if isinstance(ttl_seconds, datetime):
                self._delegate.revoke(jti, ttl_seconds)
            else:
                self._delegate.revoke(
                    jti, datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
                )
            return
        expiry = (
            ttl_seconds
            if isinstance(ttl_seconds, datetime)
            else datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        )
        self._revoked[jti] = expiry

    def is_revoked(self, jti: str) -> bool:
        if self._delegate is not None:
            return bool(self._delegate.is_revoked(jti))
        expiry = self._revoked.get(jti)
        if expiry is None:
            return False
        if expiry <= datetime.now(timezone.utc):
            self._revoked.pop(jti, None)
            return False
        return True


class LocalAuthAdapter:
    """MissionManager local auth API implemented through ``auth`` services."""

    def __init__(
        self,
        secret_key: str,
        person_repo: PersonRepository,
        cred_repo: CredentialRepository,
        token_ttl: int = 3600,
        password_policy: Optional[PasswordPolicy] = None,
        max_failed_attempts: int = 5,
        lockout_duration_seconds: int = 300,
        revocation_store=None,
        uow=None,
    ) -> None:
        if not secret_key or len(secret_key) < 32:
            raise ValueError("secret_key deve essere di almeno 32 caratteri")
        self._person_repo = person_repo
        self._uow = uow
        self._accounts = _PersonAccountRepository(person_repo, uow=uow)
        self._credentials = _CredentialRepositoryAdapter(cred_repo, uow=uow)
        self._hasher = BcryptPasswordHasher()
        self._clock = SystemClock()
        self._policy = password_policy or PasswordPolicy()
        self._revocations = _TokenRevocationAdapter(revocation_store)
        self._tokens = TokenService(
            self._accounts,
            _TokenRepository(),
            self._revocations,
            HmacTokenSigner(secret_key),
            self._clock,
            SecretsSecureRandom(),
            issuer=_LOCAL_ISSUER,
            audience=_AUDIENCE,
            access_ttl=timedelta(seconds=token_ttl),
        )
        self._authentication = CoreAuthenticationService(
            "local",
            self._accounts,
            self._credentials,
            self._hasher,
            self._clock,
            password_policy=self._policy.to_core(),
            sessions=None,
            tokens=self._tokens,
            external_identities=None,
            max_failed_attempts=max_failed_attempts,
            lockout_duration=timedelta(seconds=lockout_duration_seconds),
        )

    def set_password(
        self, person_id: UUID, password: str, must_change: bool = False
    ) -> None:
        try:
            self._policy.to_core().validate(password)
            now = self._clock.now()
            self._credentials.save(
                CoreLocalCredential(
                    account_id=AccountId(str(person_id)),
                    password_hash=self._hasher.hash(password),
                    hash_algorithm=self._hasher.algorithm,
                    hash_version=self._hasher.version,
                    failed_attempts=0,
                    locked_until=None,
                    password_changed_at=now,
                    must_change=must_change,
                )
            )
        except CoreValidationError as exc:
            raise ValidationError(str(exc), field="password") from exc

    def delete_credentials(self, person_id: UUID) -> bool:
        existing = self._credentials.get(AccountId(str(person_id)))
        if existing is None:
            return False
        self._credentials.delete(AccountId(str(person_id)))
        return True

    def password_change_required(self, person_id: UUID) -> bool:
        credential = self._credentials.get(AccountId(str(person_id)))
        return bool(credential and credential.must_change)

    def authenticate(self, username: str, password: str) -> Tuple[Person, str]:
        try:
            result = self._authentication.login_local(
                username,
                password,
                AuthContext(issue_session=False, issue_tokens=True),
            )
            with self._txn():
                person = self._person_repo.get(UUID(str(result.account_id)))
            token = result.access_token.value if result.access_token is not None else self.issue_token(person)
            return person, token
        except CoreAuthenticationError as exc:
            locked_message = self._lockout_message(username)
            if locked_message is not None:
                raise AuthenticationError(locked_message) from exc
            raise AuthenticationError(str(exc)) from exc
        except CoreValidationError as exc:
            raise ValidationError(str(exc)) from exc

    def unlock(self, person_id: UUID) -> None:
        self._credentials.reset_failures(AccountId(str(person_id)))

    def issue_token(self, person: Person) -> str:
        account = self._accounts.get_by_id(AccountId(str(person.id)))
        if account is None:
            raise AuthenticationError("Account locale non trovato")
        return self._tokens.issue_access_token(
            account,
            AuthContext(issue_session=False, issue_tokens=True),
        ).value

    def verify_token(self, token: str) -> UUID:
        try:
            principal = self._tokens.verify_access_token(token)
            return UUID(str(principal.account_id))
        except AuthError as exc:
            raise AuthenticationError(str(exc)) from exc

    def revoke_token(self, token: str) -> None:
        try:
            self._tokens.revoke_access_token(token)
        except AuthError:
            return None

    def _txn(self):
        return self._uow.transaction() if self._uow is not None else nullcontext()

    def _lockout_message(self, username: str) -> str | None:
        account = self._accounts.get_by_username(username)
        if account is None:
            return None
        credential = self._credentials.get(account.id)
        if credential is None or not credential.is_locked(self._clock.now()):
            return None
        return (
            "Account temporaneamente bloccato per troppi tentativi falliti; "
            "riprova più tardi"
        )
