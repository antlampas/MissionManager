# SPDX-License-Identifier: CC-BY-SA-4.0
"""Configurazione pytest condivisa: import path e fixture comuni.

Esegui la suite da ``implementation/``:

    python -m pytest src/test
"""
from __future__ import annotations

import pathlib
import sys
import uuid

import pytest

# Rende importabile il package ``src`` a prescindere dalla cwd di pytest.
_IMPL_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(_IMPL_DIR) not in sys.path:
    sys.path.insert(0, str(_IMPL_DIR))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.infrastructure.repositories.models import Base


@pytest.fixture
def fk_session() -> Session:
    """Session SQLAlchemy su SQLite in-memory con vincoli FK applicati.

    Replica il comportamento di MySQL/PostgreSQL (che applicano le foreign key),
    a differenza di SQLite di default.
    """
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_con, _):  # noqa: ANN001
        dbapi_con.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _set_local_env(monkeypatch, tmp_path) -> None:
    db = tmp_path / "mm.db"
    env = {
        "MISSIONMANAGER_DATABASE_URL": f"sqlite:///{db}",
        "MISSIONMANAGER_SECRET_KEY": "x" * 40,
        "MISSIONMANAGER_PERSON_BACKEND": "local",
        "MISSIONMANAGER_AUTH_BACKEND": "local",
        "MISSIONMANAGER_REST_DEV_MODE": "true",
        # Dev locale su HTTP: il cookie di sessione non dev'essere Secure.
        "MISSIONMANAGER_WEB_SECURE_COOKIES": "false",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def web_app(monkeypatch, tmp_path):
    """Coppia (app Quart Web, BootstrappedSystem) con backend locale su SQLite temporaneo."""
    _set_local_env(monkeypatch, tmp_path)
    from src.bootstrap.web import create_web_app

    return create_web_app()


@pytest.fixture
def rest_app(monkeypatch, tmp_path):
    """Coppia (app Quart REST, BootstrappedSystem) con backend locale su SQLite temporaneo."""
    _set_local_env(monkeypatch, tmp_path)
    from src.bootstrap.rest import create_rest_app

    return create_rest_app()


@pytest.fixture
def seed_admin():
    """Ritorna una funzione che crea un operatore con password locale.

    ``acl_level`` segue la convenzione del sistema ACL (DESIGN §10): più basso
    = più privilegiato; 0 è il tier amministrativo dei default di bootstrap.
    """

    def _seed(svcs, nickname: str = "admin", password: str = "ValidPassword1!", acl_level: int = 0):
        from src.application.services._shared import acl_bypass

        with acl_bypass():
            person = svcs.person.add(nicknames=[nickname])
            person = svcs.person.set_acl_profile(person.id, acl_level=acl_level)
            svcs.auth_service.set_password(uuid.UUID(person.id), password)
        return person

    return _seed
