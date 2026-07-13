# SPDX-License-Identifier: CC-BY-SA-4.0
"""Utility specifiche per il frontend REST API (Quart).

Funzioni di supporto per i router: parsing del JSON di richiesta,
paginazione, risposta di errore standardizzata, accesso a g.operator.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from quart import g, jsonify, request

from .._utils import clamp_pagination


def operator_id():
    """Restituisce l'UUID dell'operatore corrente da g, o None."""
    operator = getattr(g, "operator", None)
    return operator.id if operator is not None else None


def dto_to_dict(dto: Any) -> dict:
    """Converte un dataclass DTO in dict ricorsivo."""
    return asdict(dto)


def error_response(message: str, status_code: int, **extra) -> Any:
    """Risposta JSON di errore con struttura uniforme."""
    body = {"error": message}
    body.update(extra)
    return jsonify(body), status_code


async def parse_json_body() -> dict:
    """Parsa il body JSON della request, restituendo {} se il body è assente."""
    try:
        data = await request.get_json(silent=True)
        return data or {}
    except Exception:
        return {}


def parse_pagination(
    default_page: int = 1,
    default_page_size: int = 20,
    max_page_size: int = 200,
) -> tuple[int, int]:
    """Estrae e valida page e page_size dai query params della request corrente."""
    return clamp_pagination(
        request.args.get("page"),
        request.args.get("page_size"),
        default_page=default_page,
        default_page_size=default_page_size,
        max_page_size=max_page_size,
    )
