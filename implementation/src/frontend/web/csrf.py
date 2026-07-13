# SPDX-License-Identifier: CC-BY-SA-4.0
"""Protezione CSRF per le richieste mutanti della Web App basata su sessione."""
from __future__ import annotations

import hmac
import secrets

from quart import request, session

from ...domain.exceptions import ValidationError

_SESSION_KEY = "csrf_token"
_UNSAFE_METHODS = frozenset(("POST", "PUT", "PATCH", "DELETE"))


def get_csrf_token() -> str:
    """Restituisce (e, alla prima richiesta, genera) il token di sessione."""
    token = session.get(_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_SESSION_KEY] = token
    return token


async def validate_csrf_request() -> None:
    """Verifica header JSON o campo form per ogni richiesta mutante."""
    if request.method not in _UNSAFE_METHODS:
        return
    expected = session.get(_SESSION_KEY)
    supplied = request.headers.get("X-CSRF-Token")
    if supplied is None:
        form = await request.form
        supplied = form.get("csrf_token")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise ValidationError("Token CSRF mancante o non valido", field="csrf_token")
