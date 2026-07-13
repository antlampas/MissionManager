# SPDX-License-Identifier: CC-BY-SA-4.0
"""Helper HTTP condivisi dai frontend Quart (REST API e Web App).

Eliminano il boilerplate ripetuto negli handler: lettura dell'operatore
corrente da ``g`` e parsing del body JSON della request.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from uuid import UUID

from quart import g, request


def operator_id() -> Optional[UUID]:
    """UUID dell'operatore corrente (da ``g.operator``), o ``None`` se assente."""
    operator = getattr(g, "operator", None)
    return operator.id if operator is not None else None


async def parse_json_body() -> dict:
    """Body JSON della request corrente, o ``{}`` se assente o non valido.

    I campi obbligatori vanno validati a valle (``require_field``); i campi
    mancanti producono così un 400 di dominio uniforme invece di un 415/500.
    """
    try:
        data = await request.get_json(silent=True)
    except Exception:
        return {}
    return data or {}


async def run_blocking(callable_, /, *args, **kwargs):
    """Esegue I/O sincrono dei service fuori dal loop Quart."""
    return await asyncio.to_thread(callable_, *args, **kwargs)
