# SPDX-License-Identifier: CC-BY-SA-4.0
"""Integrazione end-to-end di plugin ed estensioni.

Verifica la catena completa: bundle su disco → registri di fiducia →
loader → registry → hook nei service / route REST / comandi CLI.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

import pytest

from src.application.services._shared import acl_bypass
from src.domain.exceptions import OperationAbortedError
from src.domain.plugins import HookPoint

_RECORDER_PLUGIN = '''
import json
import os


class Plugin:
    def execute(self, context):
        log_path = os.environ.get("MM_TEST_HOOK_LOG")
        if not log_path:
            return
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "hook": getattr(context.hook_point, "value", str(context.hook_point)),
                "payload": {k: str(v) for k, v in (context.payload or {}).items()},
                "operator": str(context.operator_id) if context.operator_id else None,
            }) + "\\n")
'''

_VETO_PLUGIN = '''
import os


class Plugin:
    def execute(self, context):
        if (
            os.environ.get("MM_TEST_ABORT_DELETE") == "1"
            and context.payload.get("entity_type") == "MISSION"
        ):
            context.abort = True
            context.abort_reason = "veto di test"
            context.user_message = "Cancellazione vietata dal plugin di test"
'''

_VETO_ECHO_PLUGIN = '''
import os


class Plugin:
    def execute(self, context):
        if os.environ.get("MM_TEST_ABORT_ECHO") == "1":
            context.abort = True
            context.abort_reason = "veto echo"
            context.user_message = "Echo vietato dal plugin di test"
'''

_ECHO_EXTENSION = '''
from src.domain.extensions import ExtensionResult


class Extension:
    def __init__(self, manifest=None, mission_svc=None, acl_svc=None,
                 event_publisher=None, hook_emitter=None, **_kwargs):
        self.manifest = manifest
        self._acl_svc = acl_svc
        self._event_publisher = event_publisher
        self._hooks = hook_emitter

    def execute(self, request):
        if self._hooks is not None:
            self._hooks.fire_before(
                "echo",
                {"params": {k: str(v) for k, v in request.params.items()}},
                operator_id=request.operator_id,
            )
        data = {
            "params": {k: str(v) for k, v in request.params.items()},
            "operator": str(request.operator_id) if request.operator_id else None,
            "has_acl_svc": self._acl_svc is not None,
            "has_event_publisher": self._event_publisher is not None,
        }
        if self._hooks is not None:
            self._hooks.fire_after(
                "echo", {}, result=data, operator_id=request.operator_id
            )
        return ExtensionResult(status_code=200, data=data)
'''


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_plugin_bundle(root, plugin_id, code, hooks, trust_level="TRUSTED", priority=0):
    bundle = root / plugin_id
    bundle.mkdir(parents=True)
    code_path = bundle / "plugin.py"
    code_path.write_text(code, encoding="utf-8")
    code_checksum = _sha256(code_path.read_bytes())
    manifest = {
        "id": plugin_id,
        "name": plugin_id,
        "version": "1.0.0",
        "description": "bundle di test",
        "hooks": hooks,
        "trust_level": trust_level,
        "priority": priority,
        "code_checksum": code_checksum,
    }
    manifest_raw = json.dumps(manifest).encode("utf-8")
    (bundle / "manifest.json").write_bytes(manifest_raw)
    return {
        "trust_level": trust_level,
        "manifest_checksum": _sha256(manifest_raw),
        "code_checksum": code_checksum,
    }


def _write_extension_bundle(root, ext_id, code, routes, commands):
    bundle = root / ext_id
    bundle.mkdir(parents=True)
    code_path = bundle / "extension.py"
    code_path.write_text(code, encoding="utf-8")
    code_checksum = _sha256(code_path.read_bytes())
    manifest = {
        "id": ext_id,
        "name": ext_id,
        "version": "1.0.0",
        "description": "estensione di test",
        "code_checksum": code_checksum,
        "provides_routes": routes,
        "provides_commands": commands,
    }
    manifest_raw = json.dumps(manifest).encode("utf-8")
    (bundle / "manifest.json").write_bytes(manifest_raw)
    return {
        "manifest_checksum": _sha256(manifest_raw),
        "code_checksum": code_checksum,
    }


@pytest.fixture
def integrated_system(monkeypatch, tmp_path):
    """(app REST, system, path log hook) con plugin ed estensioni da disco."""
    plugins_dir = tmp_path / "plugins"
    exts_dir = tmp_path / "exts"
    hook_log = tmp_path / "hooks.jsonl"

    all_hooks = [point.value for point in HookPoint] + [
        "BEFORE_EXT:echo-ext:echo",
        "AFTER_EXT:echo-ext:echo",
    ]
    trust_entries = {
        "recorder": _write_plugin_bundle(
            plugins_dir, "recorder", _RECORDER_PLUGIN, all_hooks, priority=0
        ),
        "veto-delete": _write_plugin_bundle(
            plugins_dir, "veto-delete", _VETO_PLUGIN,
            [HookPoint.BEFORE_DELETE.value], priority=50,
        ),
        "veto-echo": _write_plugin_bundle(
            plugins_dir, "veto-echo", _VETO_ECHO_PLUGIN,
            ["BEFORE_EXT:echo-ext:echo"], priority=50,
        ),
    }
    trust_registry = tmp_path / "trusted_plugins.json"
    trust_registry.write_text(json.dumps(trust_entries), encoding="utf-8")

    installed_entries = {
        "echo-ext": _write_extension_bundle(
            exts_dir,
            "echo-ext",
            _ECHO_EXTENSION,
            routes=[
                {"path": "/extensions/echo-ext/echo", "method": "GET"},
                {"path": "/extensions/echo-ext/echo", "method": "POST"},
            ],
            commands=[{"name": "echo-ext"}],
        ),
    }
    installed_registry = tmp_path / "installed_extensions.json"
    installed_registry.write_text(json.dumps(installed_entries), encoding="utf-8")

    env = {
        "MISSIONMANAGER_DATABASE_URL": f"sqlite:///{tmp_path / 'mm.db'}",
        "MISSIONMANAGER_SECRET_KEY": "x" * 40,
        "MISSIONMANAGER_PERSON_BACKEND": "local",
        "MISSIONMANAGER_AUTH_BACKEND": "local",
        "MISSIONMANAGER_REST_DEV_MODE": "true",
        "MISSIONMANAGER_WEB_SECURE_COOKIES": "false",
        "MISSIONMANAGER_PLUGINS_SCAN_PATHS": str(plugins_dir),
        "MISSIONMANAGER_PLUGINS_TRUST_REGISTRY": str(trust_registry),
        "MISSIONMANAGER_EXTENSIONS_SCAN_PATHS": str(exts_dir),
        "MISSIONMANAGER_EXTENSIONS_INSTALLED_REGISTRY": str(installed_registry),
        "MM_TEST_HOOK_LOG": str(hook_log),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("MM_TEST_ABORT_DELETE", raising=False)
    monkeypatch.delenv("MM_TEST_ABORT_ECHO", raising=False)

    from src.bootstrap.rest import create_rest_app

    app, svcs = create_rest_app()
    return app, svcs, hook_log


def _fired_hooks(hook_log) -> list[str]:
    if not hook_log.exists():
        return []
    return [
        json.loads(line)["hook"]
        for line in hook_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _bearer(svcs):
    _, token = svcs.auth_service.login_local("admin", "ValidPassword1!")
    return {"Authorization": f"Bearer {token}"}


def test_loader_registers_plugins_and_extensions(integrated_system):
    _, svcs, _ = integrated_system
    plugin_ids = {m.id for m in svcs.plugin_registry.list_plugins()}
    assert {"recorder", "veto-delete", "veto-echo"} <= plugin_ids
    ext_ids = {m.id for m in svcs.extension_registry.list()}
    assert "echo-ext" in ext_ids


def test_hooks_fire_on_every_mutating_flow(integrated_system, seed_admin):
    _, svcs, hook_log = integrated_system
    admin = seed_admin(svcs)
    op = uuid.UUID(admin.id)

    with acl_bypass():
        # Persone e gruppi
        person = svcs.person.add(["mario"], operator_id=op)
        svcs.person.update(person.id, nicknames=["mario", "super-mario"], operator_id=op)
        group = svcs.person.add_group(name="Alfa", operator_id=op)
        svcs.person.add_group_member(group.id, person.id, operator_id=op)
        svcs.person.update_group(group.id, name="Beta", operator_id=op)
        svcs.person.remove_group_member(group.id, person.id, operator_id=op)

        # Missione, assignment, attività
        mission = svcs.mission.create(
            title="Op", desc="",
            objectives=[{"description": "O", "activities": [{"title": "A"}]}],
            operator_id=op,
        )
        assignment = svcs.assignment.create(mission.id, operator_id=op)
        svcs.assignment.assign(assignment.id, "PERSON", person.id, operator_id=op)
        objective_id = svcs.assignment.get(assignment.id, operator_id=op).objectives[0].id
        activity = svcs.activity.list_by_objective(objective_id, operator_id=op)[0]
        svcs.activity.assign_to(activity.id, person.id, operator_id=op)
        svcs.activity.unassign(activity.id, person.id, operator_id=op)
        svcs.activity.assign_to(activity.id, person.id, operator_id=op)
        svcs.activity.update_status(activity.id, "IN_PROGRESS", operator_id=op)

        # Badge
        svcs.badge.create("Coraggio", "desc", operator_id=op)

        # Cancellazioni
        svcs.assignment.delete(assignment.id, operator_id=op)
        svcs.mission.delete(mission.id, operator_id=op)
        svcs.person.remove_group(group.id, operator_id=op)
        svcs.person.remove(person.id, operator_id=op)

    fired = set(_fired_hooks(hook_log))
    expected = {
        "BEFORE_CREATE_PERSON", "AFTER_CREATE_PERSON",
        "BEFORE_UPDATE_PERSON", "AFTER_UPDATE_PERSON",
        "BEFORE_CREATE_GROUP", "AFTER_CREATE_GROUP",
        "BEFORE_UPDATE_GROUP", "AFTER_UPDATE_GROUP",
        "BEFORE_MANAGE_MEMBERS", "AFTER_MANAGE_MEMBERS",
        "BEFORE_CREATE_MISSION", "AFTER_CREATE_MISSION",
        "BEFORE_CREATE_ASSIGNMENT", "AFTER_CREATE_ASSIGNMENT",
        "BEFORE_ASSIGN", "AFTER_ASSIGN",
        "BEFORE_UPDATE_STATUS", "AFTER_UPDATE_STATUS",
        "BEFORE_CREATE_BADGE", "AFTER_CREATE_BADGE",
        "BEFORE_DELETE", "AFTER_DELETE",
    }
    assert expected <= fired, f"hook mancanti: {sorted(expected - fired)}"

    # Le cancellazioni coprono tutti i tipi di entità.
    deleted_types = {
        json.loads(line)["payload"]["entity_type"]
        for line in hook_log.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line)["hook"] == "AFTER_DELETE"
    }
    assert deleted_types == {"MISSION", "ASSIGNMENT", "PERSON", "GROUP"}

    # ASSIGN copre assignment e attività, con azioni ASSIGN e UNASSIGN.
    assign_records = [
        json.loads(line)["payload"]
        for line in hook_log.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line)["hook"] == "AFTER_ASSIGN"
    ]
    assert {p["entity_type"] for p in assign_records} == {"ASSIGNMENT", "ACTIVITY"}
    assert {p["action"] for p in assign_records} == {"ASSIGN", "UNASSIGN"}


def test_trusted_before_delete_hook_vetoes_mission_deletion(
    integrated_system, seed_admin, monkeypatch
):
    _, svcs, _ = integrated_system
    admin = seed_admin(svcs)
    op = uuid.UUID(admin.id)

    with acl_bypass():
        mission = svcs.mission.create(
            title="Da proteggere", desc="",
            objectives=[{"description": "O", "activities": [{"title": "A"}]}],
            operator_id=op,
        )

    monkeypatch.setenv("MM_TEST_ABORT_DELETE", "1")
    with acl_bypass():
        with pytest.raises(OperationAbortedError, match="Cancellazione vietata"):
            svcs.mission.delete(mission.id, operator_id=op)
        # La missione esiste ancora: il veto ha bloccato la cancellazione.
        assert svcs.mission.get(mission.id, operator_id=op).id == mission.id

    monkeypatch.delenv("MM_TEST_ABORT_DELETE")
    with acl_bypass():
        svcs.mission.delete(mission.id, operator_id=op)


def test_first_boot_admin_creation_fires_hooks_without_operator(
    integrated_system, seed_admin
):
    """La creazione del primo admin (flusso anonimo) non deve fallire con i
    hook attivi: l'operatore nel contesto resta None."""
    _, svcs, hook_log = integrated_system
    seed_admin(svcs)
    records = [
        json.loads(line)
        for line in hook_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    created = [r for r in records if r["hook"] == "AFTER_CREATE_PERSON"]
    assert created and created[0]["operator"] is None


def test_rest_extension_routes_get_post_and_query_params(integrated_system, seed_admin):
    app, svcs, _ = integrated_system
    seed_admin(svcs)
    headers = _bearer(svcs)

    async def scenario():
        client = app.test_client()

        r = await client.get(
            "/api/extensions/echo-ext/echo?x=1", headers=headers
        )
        assert r.status_code == 200
        data = (await r.get_json())["data"]
        assert data["params"]["x"] == "1"
        assert data["operator"] is not None
        assert data["has_acl_svc"] is True
        assert data["has_event_publisher"] is True

        r = await client.post(
            "/api/extensions/echo-ext/echo", headers=headers, json={"y": "2"}
        )
        assert r.status_code == 200
        data = (await r.get_json())["data"]
        assert data["params"]["y"] == "2"

        # Body JSON non-oggetto → 400, non 500.
        r = await client.post(
            "/api/extensions/echo-ext/echo", headers=headers, json=["lista"]
        )
        assert r.status_code == 400

        # Anonimo → 401 (EXECUTE/VIEW su SYSTEM non concessi al pubblico).
        r = await client.get("/api/extensions/echo-ext/echo")
        assert r.status_code == 401

    asyncio.run(scenario())


def _build_cli(svcs, admin):
    from src.frontend.cli.app import create_cli

    with svcs.uow.transaction():
        admin_person = svcs.person_repo.get(uuid.UUID(admin.id))

    class _Provider:
        def get_current_operator(self):
            return admin_person

    return create_cli(
        mission_svc=svcs.mission,
        assignment_svc=svcs.assignment,
        activity_svc=svcs.activity,
        badge_svc=svcs.badge,
        person_svc=svcs.person,
        acl_svc=svcs.acl,
        extension_registry=svcs.extension_registry,
        auth_policy=svcs.auth_policy,
        operator_provider=_Provider(),
    )


def test_cli_extension_command_executes(integrated_system, seed_admin):
    from click.testing import CliRunner

    _, svcs, _ = integrated_system
    admin = seed_admin(svcs)
    cli = _build_cli(svcs, admin)
    assert "echo-ext" in cli.commands

    runner = CliRunner()
    result = runner.invoke(cli, ["echo-ext", "--param", "k=v"], obj={})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["params"]["k"] == "v"
    assert payload["operator"] == admin.id


# ---------------------------------------------------------------------------
# Hook point custom delle estensioni (Livello 2)
# ---------------------------------------------------------------------------

def test_extension_custom_hooks_fire_via_rest(integrated_system, seed_admin):
    app, svcs, hook_log = integrated_system
    seed_admin(svcs)
    headers = _bearer(svcs)

    async def scenario():
        client = app.test_client()
        r = await client.get("/api/extensions/echo-ext/echo?x=1", headers=headers)
        assert r.status_code == 200

    asyncio.run(scenario())

    records = [
        json.loads(line)
        for line in hook_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    custom = [r for r in records if r["hook"].endswith("EXT:echo-ext:echo")]
    assert {r["hook"] for r in custom} == {
        "BEFORE_EXT:echo-ext:echo", "AFTER_EXT:echo-ext:echo"
    }
    # L'operatore autenticato arriva fino agli hook custom.
    assert all(r["operator"] is not None for r in custom)


def test_trusted_plugin_vetoes_extension_custom_hook_rest(
    integrated_system, seed_admin, monkeypatch
):
    app, svcs, _ = integrated_system
    seed_admin(svcs)
    headers = _bearer(svcs)

    monkeypatch.setenv("MM_TEST_ABORT_ECHO", "1")

    async def scenario():
        client = app.test_client()
        r = await client.get("/api/extensions/echo-ext/echo?x=1", headers=headers)
        assert r.status_code == 422
        body = await r.get_json()
        assert "Echo vietato" in body["error"]

    asyncio.run(scenario())

    monkeypatch.delenv("MM_TEST_ABORT_ECHO")

    async def scenario_ok():
        client = app.test_client()
        r = await client.get("/api/extensions/echo-ext/echo?x=1", headers=headers)
        assert r.status_code == 200

    asyncio.run(scenario_ok())


def test_trusted_plugin_vetoes_extension_custom_hook_cli(
    integrated_system, seed_admin, monkeypatch
):
    from click.testing import CliRunner

    _, svcs, _ = integrated_system
    admin = seed_admin(svcs)
    cli = _build_cli(svcs, admin)

    monkeypatch.setenv("MM_TEST_ABORT_ECHO", "1")
    runner = CliRunner()
    result = runner.invoke(cli, ["echo-ext"], obj={})
    assert result.exit_code == 1
    assert "Echo vietato" in result.output
