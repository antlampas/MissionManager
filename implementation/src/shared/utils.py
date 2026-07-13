# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def new_id() -> UUID:
    return uuid4()


def generate_id() -> str:
    """Genera un UUID4 come stringa (compat. con codice che usa str, non UUID)."""
    return str(uuid4())


def parse_datetime(s: str) -> datetime:
    """Parsa una stringa ISO-8601 in datetime aware (UTC).

    Python < 3.11 non gestisce il suffisso "Z"; lo normalizza prima del parse.
    """
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def validate_string_length(
    value: str, min_len: int, max_len: int, field_name: str
) -> None:
    from .errors import ValidationError

    if not (min_len <= len(value) <= max_len):
        raise ValidationError(
            f"{field_name} deve essere tra {min_len} e {max_len} caratteri",
            field=field_name,
        )


def validate_pagination(page: int, page_size: int, max_page_size: int = 1000) -> None:
    from .errors import ValidationError

    if page < 1:
        raise ValidationError("Il numero di pagina deve essere >= 1", field="page")
    if not (1 <= page_size <= max_page_size):
        raise ValidationError(
            f"page_size deve essere compreso tra 1 e {max_page_size}",
            field="page_size",
        )
