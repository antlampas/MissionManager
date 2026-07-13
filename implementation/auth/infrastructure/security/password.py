# SPDX-License-Identifier: CC-BY-SA-4.0
"""Password hashing adapters."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass

from auth.domain.errors import ConfigurationError, ValidationError

MAX_BCRYPT_BYTES = 72


@dataclass(frozen=True)
class Pbkdf2PasswordHasher:
    """Stdlib hasher for tests/dev when Argon2id is not installed."""

    iterations: int = 600_000
    salt_bytes: int = 16
    algorithm: str = "pbkdf2_sha256"
    version: int = 1

    def hash(self, password: str) -> str:
        salt = os.urandom(self.salt_bytes)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, self.iterations)
        return "$".join(
            (
                self.algorithm,
                str(self.version),
                str(self.iterations),
                _b64(salt),
                _b64(digest),
            )
        )

    def verify(self, password: str, stored_hash: str) -> bool:
        try:
            algorithm, version, iterations, salt_b64, digest_b64 = stored_hash.split("$", 4)
            if algorithm != self.algorithm:
                return False
            salt = _unb64(salt_b64)
            expected = _unb64(digest_b64)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False

    def needs_rehash(self, stored_hash: str) -> bool:
        try:
            algorithm, version, iterations, *_ = stored_hash.split("$", 4)
        except ValueError:
            return True
        return algorithm != self.algorithm or int(version) != self.version or int(iterations) != self.iterations


class Argon2idPasswordHasher:
    algorithm = "argon2id"
    version = 1

    def __init__(self, **kwargs: object) -> None:
        try:
            from argon2 import PasswordHasher as _ArgonPasswordHasher
            from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError
        except ImportError as exc:
            raise ConfigurationError("argon2-cffi is required for Argon2idPasswordHasher") from exc
        self._hasher = _ArgonPasswordHasher(**kwargs)
        self._invalid_hash_error = InvalidHashError
        self._verify_mismatch_error = VerifyMismatchError
        self._verification_error = VerificationError

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, stored_hash: str) -> bool:
        try:
            return bool(self._hasher.verify(stored_hash, password))
        except (self._invalid_hash_error, self._verify_mismatch_error, self._verification_error):
            return False

    def needs_rehash(self, stored_hash: str) -> bool:
        try:
            return bool(self._hasher.check_needs_rehash(stored_hash))
        except self._invalid_hash_error:
            return True


class BcryptPasswordHasher:
    algorithm = "bcrypt"
    version = 1

    def __init__(self, *, reject_long_passwords: bool = True, rounds: int = 12) -> None:
        try:
            import bcrypt
        except ImportError as exc:
            raise ConfigurationError("bcrypt is required for BcryptPasswordHasher") from exc
        self._bcrypt = bcrypt
        self._reject_long = reject_long_passwords
        self._rounds = rounds

    def hash(self, password: str) -> str:
        data = self._password_bytes(password)
        return self._bcrypt.hashpw(data, self._bcrypt.gensalt(rounds=self._rounds)).decode("ascii")

    def verify(self, password: str, stored_hash: str) -> bool:
        try:
            data = self._password_bytes(password, for_verify=True)
            return bool(self._bcrypt.checkpw(data, stored_hash.encode("ascii")))
        except (ValueError, UnicodeEncodeError):
            return False

    def needs_rehash(self, stored_hash: str) -> bool:
        return not stored_hash.startswith("$2")

    def _password_bytes(self, password: str, *, for_verify: bool = False) -> bytes:
        data = password.encode("utf-8")
        if len(data) <= MAX_BCRYPT_BYTES:
            return data
        if self._reject_long:
            raise ValidationError("bcrypt password exceeds 72 bytes")
        return data[:MAX_BCRYPT_BYTES]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
