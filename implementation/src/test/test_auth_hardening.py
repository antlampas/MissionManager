# SPDX-License-Identifier: CC-BY-SA-4.0
"""Hardening dell'autenticazione locale: password policy, lockout, must_change.

Verifica le migliorie di sicurezza portate sul backend locale:
  - :class:`PasswordPolicy` (lunghezza minima, classi di caratteri, tetto 72 byte);
  - account lockout dopo troppi tentativi falliti, con conteggio che persiste
    nonostante il rollback del caso d'uso sull'eccezione;
  - ``must_change_password`` impostato/azzerato correttamente.
"""
import uuid

import pytest

from src.domain.exceptions import AuthenticationError, ValidationError
from src.infrastructure.auth.local import PasswordPolicy


# --------------------------------------------------------------------------- #
# PasswordPolicy (funzione pura)
# --------------------------------------------------------------------------- #

def test_password_policy_min_length():
    policy = PasswordPolicy(min_length=8)
    with pytest.raises(ValidationError):
        policy.validate("corta")
    policy.validate("Abbastanza1!")  # non solleva


def test_password_policy_character_classes():
    policy = PasswordPolicy(
        min_length=8,
        require_uppercase=True,
        require_digit=True,
        require_special=True,
    )
    with pytest.raises(ValidationError):
        policy.validate("tuttominuscolo")  # manca maiuscola/cifra/speciale
    policy.validate("Abcdefghijk1!")  # soddisfa tutte le classi


def test_password_policy_72_byte_cap():
    policy = PasswordPolicy(min_length=8)
    with pytest.raises(ValidationError):
        policy.validate("a" * 73)


def test_password_policy_defaults_are_strict():
    # Default forte: lunghezza minima + maiuscola + cifra + carattere speciale.
    with pytest.raises(ValidationError):
        PasswordPolicy().validate("password123")
    PasswordPolicy().validate("ValidPassword1!")


# --------------------------------------------------------------------------- #
# Account lockout + must_change (integrazione con lo stack locale reale)
# --------------------------------------------------------------------------- #

def test_lockout_after_failed_attempts(rest_app, seed_admin):
    _app, svcs = rest_app
    seed_admin(svcs, nickname="u1", acl_level=0)  # password: ValidPassword1!

    # 4 tentativi errati (< soglia 5): l'account non è ancora bloccato e una
    # password corretta autentica e azzera il conteggio.
    for _ in range(4):
        with pytest.raises(AuthenticationError):
            svcs.auth_service.login_local("u1", "sbagliata")
    person, token = svcs.auth_service.login_local("u1", "ValidPassword1!")
    assert token

    # Raggiunta la soglia (5 fallimenti consecutivi) l'account è bloccato anche
    # con la password corretta — il conteggio è persistito malgrado i rollback.
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            svcs.auth_service.login_local("u1", "sbagliata")
    with pytest.raises(AuthenticationError) as exc:
        svcs.auth_service.login_local("u1", "ValidPassword1!")
    assert "bloccato" in str(exc.value).lower()


def test_reset_password_clears_lockout(rest_app, seed_admin):
    _app, svcs = rest_app
    person = seed_admin(svcs, nickname="u2", acl_level=0)
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            svcs.auth_service.login_local("u2", "sbagliata")
    # Impostare una nuova password sblocca l'account.
    svcs.auth_service.set_password(uuid.UUID(person.id), "ValidPassword2!")
    _p, token = svcs.auth_service.login_local("u2", "ValidPassword2!")
    assert token


def test_must_change_password_flag(rest_app, seed_admin):
    _app, svcs = rest_app
    person = seed_admin(svcs, nickname="u3", acl_level=0)
    pid = uuid.UUID(person.id)

    # Password impostata da un amministratore per l'operatore → cambio forzato.
    svcs.auth_service.set_password(pid, "TempPassword1!", must_change=True)
    assert svcs.auth_service.password_change_required(pid) is True

    # Il cambio self-service azzera il flag.
    svcs.auth_service.set_password(pid, "UserChosen1!", must_change=False)
    assert svcs.auth_service.password_change_required(pid) is False
