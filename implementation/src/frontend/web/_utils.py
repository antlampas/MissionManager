# SPDX-License-Identifier: CC-BY-SA-4.0
"""Utility specifiche per il frontend Web App (Quart, route HTML/JSON).

Funzioni di supporto per i handler: accesso alla sessione, risposta di errore
HTML o JSON, redirect sicuri.
"""
from __future__ import annotations

from typing import Any

from quart import Response, jsonify, redirect, session, url_for

_SESSION_OPERATOR_KEY = "operator_id"


def get_session_operator_id() -> str | None:
    """Restituisce l'UUID dell'operatore dalla sessione, o None se non autenticato."""
    return session.get(_SESSION_OPERATOR_KEY)


def set_session_operator_id(operator_id: str) -> None:
    session[_SESSION_OPERATOR_KEY] = operator_id


def clear_session() -> None:
    session.clear()


def json_error(message: str, status_code: int, **extra) -> Any:
    """Risposta JSON di errore con struttura uniforme per la Web App."""
    body = {"error": message}
    body.update(extra)
    return jsonify(body), status_code


def safe_redirect(target: str, fallback: str = "/") -> Response:
    """Redirect sicuro: usa target solo se è un percorso relativo (no open redirect)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return redirect(target)
    return redirect(fallback)
