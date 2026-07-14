# SPDX-License-Identifier: CC-BY-SA-4.0
"""Semantica dell'ExtensionRegistry: namespace, collisioni, dispatch di execute."""
from __future__ import annotations

import pytest

from src.application.extension_registry import ExtensionRegistry, accepts_subject
from src.domain.exceptions import ExtensionConflictError, NotFoundError
from src.domain.extensions import (
    CommandSpec,
    ExtensionManifest,
    ExtensionRequest,
    ExtensionResult,
    RouteSpec,
)


def _extension(ext_id, routes=(), commands=(), execute=None):
    class _Ext:
        manifest = ExtensionManifest(
            id=ext_id,
            name=ext_id,
            version="1.0.0",
            description="",
            provides_routes=list(routes),
            provides_commands=list(commands),
        )

    ext = _Ext()
    ext.execute = execute or (lambda request: ExtensionResult(status_code=200, body={}))
    return ext


def test_route_namespace_enforced():
    registry = ExtensionRegistry()
    outside = _extension("report", routes=[RouteSpec(path="/report/x", method="GET")])
    with pytest.raises(ExtensionConflictError, match="namespace"):
        registry.register(outside)


def test_route_collision_between_extensions():
    registry = ExtensionRegistry()
    registry.register(_extension(
        "first", routes=[RouteSpec(path="/extensions/first/x", method="GET")]
    ))
    # Un'estensione non può dichiarare route nel namespace di un'altra.
    with pytest.raises(ExtensionConflictError, match="namespace"):
        registry.register(_extension(
            "second", routes=[RouteSpec(path="/extensions/first/x", method="GET")]
        ))


def test_route_collision_within_same_manifest():
    registry = ExtensionRegistry()
    duplicated = _extension("dup", routes=[
        RouteSpec(path="/extensions/dup/x", method="GET"),
        RouteSpec(path="/extensions/dup/x", method="GET"),
    ])
    with pytest.raises(ExtensionConflictError, match="Collisione di route"):
        registry.register(duplicated)
    # Registrazione atomica: nulla è rimasto registrato.
    registry.register(_extension(
        "dup2", routes=[RouteSpec(path="/extensions/dup2/x", method="GET")]
    ))


def test_same_path_different_methods_allowed():
    registry = ExtensionRegistry()
    registry.register(_extension("multi", routes=[
        RouteSpec(path="/extensions/multi/x", method="GET"),
        RouteSpec(path="/extensions/multi/x", method="POST"),
    ]))
    assert registry.get("multi") is not None


def test_command_collision_between_extensions():
    registry = ExtensionRegistry()
    registry.register(_extension("first", commands=[CommandSpec(name="report")]))
    with pytest.raises(ExtensionConflictError, match="comando"):
        registry.register(_extension("second", commands=[CommandSpec(name="report")]))


def test_unregister_frees_routes_and_commands():
    registry = ExtensionRegistry()
    registry.register(_extension(
        "gone",
        routes=[RouteSpec(path="/extensions/gone/x", method="GET")],
        commands=[CommandSpec(name="gone-cmd")],
    ))
    registry.unregister("gone")
    # Route e comando tornano disponibili (stesso id, nuova istanza).
    registry.register(_extension(
        "gone",
        routes=[RouteSpec(path="/extensions/gone/x", method="GET")],
        commands=[CommandSpec(name="gone-cmd")],
    ))


def test_execute_unknown_extension_raises_not_found():
    registry = ExtensionRegistry()
    with pytest.raises(NotFoundError):
        registry.execute("missing", ExtensionRequest())


def test_execute_single_parameter_signature():
    registry = ExtensionRegistry()
    registry.register(_extension(
        "single", execute=lambda request: ExtensionResult(status_code=200, body="ok")
    ))
    result = registry.execute("single", ExtensionRequest())
    assert result.body == "ok"


def test_execute_passes_subject_to_two_parameter_signature():
    registry = ExtensionRegistry()
    registry.register(_extension(
        "pair",
        execute=lambda request, subject: ExtensionResult(status_code=200, body=subject),
    ))
    result = registry.execute("pair", ExtensionRequest(subject="il-soggetto"))
    assert result.body == "il-soggetto"


def test_execute_with_var_keyword_only_does_not_get_subject():
    """``**kwargs`` non può ricevere un posizionale: non va contato."""
    def _execute(request, **kwargs):
        return ExtensionResult(status_code=200, body=kwargs)

    registry = ExtensionRegistry()
    registry.register(_extension("kw", execute=_execute))
    result = registry.execute("kw", ExtensionRequest(subject="ignorato"))
    assert result.body == {}


def test_execute_with_var_positional_receives_subject():
    def _execute(request, *args):
        return ExtensionResult(status_code=200, body=list(args))

    registry = ExtensionRegistry()
    registry.register(_extension("varpos", execute=_execute))
    result = registry.execute("varpos", ExtensionRequest(subject="extra"))
    assert result.body == ["extra"]


def test_accepts_subject_handles_unsignaturable_callables():
    assert accepts_subject(dict) in (True, False)  # non deve sollevare


def test_extension_result_data_alias():
    result = ExtensionResult(status_code=201, data={"k": "v"})
    assert result.body == {"k": "v"}
    assert result.data == {"k": "v"}
    result.data = {"nuovo": 1}
    assert result.body == {"nuovo": 1}
