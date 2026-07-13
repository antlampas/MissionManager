# SPDX-License-Identifier: CC-BY-SA-4.0
"""Regressioni per configurazione e importabilità dei moduli."""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import acl
import auth
import src
from src.config import RealtimeConfigLoader, WebConfigLoader
from src.domain.exceptions import ValidationError
from src.infrastructure.repositories.system_state_repository import (
    SqlAlchemySystemStateRepository,
)


def test_all_modules_import_without_missing_symbols():
    """Import reale: compileall non intercetta simboli mancanti a import-time."""
    skip = {"src.asgi_rest", "src.asgi_web"}
    failed = []
    for module in pkgutil.walk_packages(src.__path__, prefix="src."):
        name = module.name
        if name in skip or name.startswith("src.test"):
            continue
        try:
            importlib.import_module(name)
        except Exception as exc:
            failed.append(f"{name}: {type(exc).__name__}: {exc}")

    assert not failed, "\n".join(failed)


def test_runtime_acl_and_auth_packages_import_without_missing_symbols():
    """I package standalone ``acl`` e ``auth`` sono parte del runtime."""
    failed = []
    for package, prefix in ((acl, "acl."), (auth, "auth.")):
        for module in pkgutil.walk_packages(package.__path__, prefix=prefix):
            try:
                importlib.import_module(module.name)
            except Exception as exc:
                failed.append(f"{module.name}: {type(exc).__name__}: {exc}")

    assert not failed, "\n".join(failed)


def test_realtime_config_loads_from_file_and_env(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
web:
  secure_cookies: "off"
realtime:
  redis_url: redis://file-redis:6379/0
  redis_prefix: file-prefix
""",
        encoding="utf-8",
    )

    web = WebConfigLoader.load(str(config_file))
    realtime = RealtimeConfigLoader.load(str(config_file))
    assert web.secure_cookies is False
    assert realtime.redis_url == "redis://file-redis:6379/0"
    assert realtime.redis_prefix == "file-prefix"

    monkeypatch.setenv("MISSIONMANAGER_REDIS_URL", "redis://env-redis:6379/1")
    monkeypatch.setenv("MISSIONMANAGER_REDIS_PREFIX", "env-prefix")
    realtime = RealtimeConfigLoader.load(str(config_file))
    assert realtime.redis_url == "redis://env-redis:6379/1"
    assert realtime.redis_prefix == "env-prefix"


def test_system_state_repository_claim_is_unique(fk_session):
    repo = SqlAlchemySystemStateRepository(fk_session)

    claim_id = repo.claim_initial_admin()
    with pytest.raises(ValidationError, match="bootstrap"):
        repo.claim_initial_admin()

    repo.release_initial_admin(claim_id)
    assert repo.claim_initial_admin()
