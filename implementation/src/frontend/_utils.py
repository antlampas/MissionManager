# SPDX-License-Identifier: CC-BY-SA-4.0
"""Utility di validazione condivise tra i frontend (API, Web, CLI).

Pura logica dati, senza dipendenze da Quart o Click.
"""
from __future__ import annotations

from ..shared.errors import ValidationError


def require_field(data: dict, field: str) -> object:
    """Restituisce data[field], sollevando ValidationError se assente o None."""
    value = data.get(field)
    if value is None:
        raise ValidationError(f"Campo obbligatorio mancante: {field!r}", field=field)
    return value


def clamp_pagination(
    page,
    page_size,
    default_page: int = 1,
    default_page_size: int = 20,
    max_page_size: int = 200,
) -> tuple[int, int]:
    """Normalizza parametri page/page_size provenienti da query string."""
    try:
        parsed_page = int(page) if page not in (None, "") else default_page
        parsed_size = int(page_size) if page_size not in (None, "") else default_page_size
    except (TypeError, ValueError):
        raise ValidationError("page e page_size devono essere interi", field="pagination")

    if parsed_page < 1:
        raise ValidationError("page deve essere >= 1", field="page")
    if parsed_size < 1:
        raise ValidationError("page_size deve essere >= 1", field="page_size")

    return parsed_page, min(parsed_size, max_page_size)
