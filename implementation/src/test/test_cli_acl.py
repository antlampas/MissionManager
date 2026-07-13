# SPDX-License-Identifier: CC-BY-SA-4.0
"""Enforcement ACL della CLI: require_acl + comandi acl (DESIGN §10)."""
import uuid

import pytest


def _make_cli(monkeypatch, tmp_path, operator_id=None):
    db = tmp_path / "mm.db"
    env = {
        "MISSIONMANAGER_DATABASE_URL": f"sqlite:///{db}",
        "MISSIONMANAGER_SECRET_KEY": "x" * 40,
        "MISSIONMANAGER_PERSON_BACKEND": "local",
        "MISSIONMANAGER_AUTH_BACKEND": "local",
    }
    if operator_id is not None:
        env["MISSIONMANAGER_CLI_IDENTITY_MODE"] = "user"
        env["MISSIONMANAGER_OPERATOR_ID"] = operator_id
    else:
        env["MISSIONMANAGER_CLI_IDENTITY_MODE"] = "anonymous"
        monkeypatch.delenv("MISSIONMANAGER_OPERATOR_ID", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    from src.bootstrap.cli import create_cli_app

    return create_cli_app()


def _seed_admin_direct(monkeypatch, tmp_path):
    """Prepara il DB con un amministratore e ne restituisce l'id."""
    app = _make_cli(monkeypatch, tmp_path)  # bootstrap anonimo per i service
    # accede ai service tramite il contesto Click non è possibile qui: si
    # ricostruisce il sistema per la semina
    from src.bootstrap.common import build_system_for_cli
    from src.application.services._shared import acl_bypass

    svcs = build_system_for_cli()
    with acl_bypass():
        person = svcs.person.add(nicknames=["admin"])
        svcs.person.set_acl_profile(person.id, acl_level=0)
    return person.id


def test_anonymous_operator_is_denied(monkeypatch, tmp_path, capsys):
    _seed_admin_direct(monkeypatch, tmp_path)
    app = _make_cli(monkeypatch, tmp_path)  # identity_mode=anonymous

    with pytest.raises(SystemExit):
        app.run(args=["mission", "list"], standalone_mode=False)
    assert "Accesso negato dalle ACL" in capsys.readouterr().err


def test_admin_operator_full_flow(monkeypatch, tmp_path, capsys):
    admin_id = _seed_admin_direct(monkeypatch, tmp_path)
    app = _make_cli(monkeypatch, tmp_path, operator_id=admin_id)

    app.run(args=["mission", "list"], standalone_mode=False)
    app.run(
        args=[
            "mission", "create", "--title", "Op", "--objectives",
            '[{"description":"O","activities":[{"title":"A"}]}]',
        ],
        standalone_mode=False,
    )
    out = capsys.readouterr().out
    assert "Missione creata" in out

    # gestione entry via CLI (autoprotetta dal service, admin ok)
    app.run(
        args=[
            "acl", "add",
            "--resource-type", "MISSION", "--resource-id", "*",
            "--operation", "VIEW", "--permission", "ALLOW",
            "--group", "viewers",
        ],
        standalone_mode=False,
    )
    out = capsys.readouterr().out
    assert "Entry creata" in out

    app.run(args=["acl", "list"], standalone_mode=False)
    out = capsys.readouterr().out
    assert "viewers" in out

    # assegnazione profilo (MANAGE_PROFILES)
    app.run(args=["person", "add", "--nickname", "op1"], standalone_mode=False)
    out = capsys.readouterr().out
    person_id = out.split("Persona creata: ")[1].split(" ")[0]
    app.run(
        args=["person", "set-acl", person_id, "--acl-level", "50",
              "--acl-group", "ops"],
        standalone_mode=False,
    )
    assert "Profilo ACL aggiornato" in capsys.readouterr().out

    app.run(args=["person", "group-add", "--name", "Ops"], standalone_mode=False)
    out = capsys.readouterr().out
    group_id = out.split("Gruppo creato: ")[1].strip()
    app.run(
        args=[
            "person", "group-update", group_id,
            "--name", "Ops Nord",
            "--zone-type", "GEOGRAPHIC",
            "--zone-desc", "nord",
        ],
        standalone_mode=False,
    )
    assert "Gruppo aggiornato" in capsys.readouterr().out


def test_low_privilege_operator_is_denied_on_writes(monkeypatch, tmp_path, capsys):
    admin_id = _seed_admin_direct(monkeypatch, tmp_path)
    admin_app = _make_cli(monkeypatch, tmp_path, operator_id=admin_id)
    admin_app.run(args=["person", "add", "--nickname", "viewer"], standalone_mode=False)
    out = capsys.readouterr().out
    viewer_id = out.split("Persona creata: ")[1].split(" ")[0]
    admin_app.run(
        args=["person", "set-acl", viewer_id, "--acl-level", "100"],
        standalone_mode=False,
    )
    capsys.readouterr()

    viewer_app = _make_cli(monkeypatch, tmp_path, operator_id=viewer_id)
    # lettura consentita dalla soglia di default
    viewer_app.run(args=["mission", "list"], standalone_mode=False)
    # scrittura negata
    with pytest.raises(SystemExit):
        viewer_app.run(
            args=[
                "mission", "create", "--title", "X", "--objectives",
                '[{"description":"O","activities":[{"title":"A"}]}]',
            ],
            standalone_mode=False,
        )
    assert "Accesso negato dalle ACL" in capsys.readouterr().err
    # gestione entry negata dal service (MANAGE_ACL)
    with pytest.raises(SystemExit):
        viewer_app.run(args=["acl", "list"], standalone_mode=False)
