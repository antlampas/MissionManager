# SPDX-License-Identifier: CC-BY-SA-4.0
"""Utility specifiche per il frontend CLI (Click).

Funzioni di supporto per i comandi Click: enforcement ACL all'ingresso dei
comandi, output tabulare, JSON pretty-print, gestione errori coerente con i
codici di uscita.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from functools import wraps
from typing import Any, Optional
from uuid import UUID

import click

from .formatter import OutputFormatter
from ...application.authorization import AuthorizationPolicy
from ...application.services._shared import reset_current_operator_id, set_current_operator_id
from ...domain.acl import Operation, ResourceRef, SYSTEM_RESOURCE
from ...domain.enums import ResourceType


def require_acl(
    operation: Operation,
    resource_type: Optional[ResourceType] = None,
    resource_param: Optional[str] = None,
):
    """Enforcement ACL all'ingresso di un comando CLI (DESIGN §10).

    Mappa il comando su ``(Operation, ResourceRef)`` e interroga
    ``AuthorizationPolicy.is_allowed`` prima di eseguirlo:

    - ``resource_type=None`` → ambito ``SYSTEM:global`` (creazioni, privilegi);
    - ``resource_param=None`` → radice del tipo (es. LIST su ``MISSION:*``);
    - altrimenti l'id della risorsa è letto dall'argomento/opzione Click
      indicato da ``resource_param``.

    In modalità anonima l'operatore è assente: vale il profilo anonimo
    implicito (le sole concessioni PUBLIC di lettura possono passare).

    Vive qui (modulo foglia) e non in ``app.py`` per evitare l'import circolare
    ``app`` → ``commands.*`` → ``app`` (i comandi importano solo questo modulo).
    """

    def decorator(f):
        @wraps(f)
        @click.pass_context
        def wrapper(ctx, *args, **kwargs):
            if resource_type is None:
                resource = SYSTEM_RESOURCE
            elif resource_param is None:
                resource = ResourceRef.type_root(resource_type)
            else:
                raw = kwargs.get(resource_param)
                try:
                    rid: UUID | str = UUID(str(raw))
                except ValueError:
                    rid = str(raw)
                resource = ResourceRef(resource_type, rid)

            operator = ctx.obj.get("operator")
            auth_policy: AuthorizationPolicy = ctx.obj["auth_policy"]
            if not auth_policy.is_allowed(
                operator.id if operator is not None else None, operation, resource
            ):
                OutputFormatter.error(
                    f"Accesso negato dalle ACL (operazione {operation.value})"
                )
                raise SystemExit(1)
            token = set_current_operator_id(operator.id if operator is not None else None)
            try:
                return ctx.invoke(f, *args, **kwargs)
            finally:
                reset_current_operator_id(token)

        return wrapper

    return decorator


def echo_json(data: Any) -> None:
    """Stampa data come JSON indentato su stdout."""
    click.echo(json.dumps(data, indent=2, default=str))


def echo_success(msg: str) -> None:
    click.echo(f"OK  {msg}")


def echo_error(msg: str, exit_code: int = 1) -> None:
    click.echo(f"ERR {msg}", err=True)
    sys.exit(exit_code)


def dto_to_dict(dto: Any) -> dict:
    """Converte un dataclass DTO in dict ricorsivo (per serializzazione JSON)."""
    return asdict(dto)


def print_table(rows: list[dict], columns: list[str]) -> None:
    """Stampa una tabella ASCII con le colonne indicate.

    rows: lista di dict; columns: chiavi da visualizzare nell'ordine indicato.
    """
    if not rows:
        click.echo("(nessun risultato)")
        return

    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            widths[col] = max(widths[col], len(str(row.get(col, ""))))

    header = "  ".join(col.ljust(widths[col]) for col in columns)
    separator = "  ".join("-" * widths[col] for col in columns)
    click.echo(header)
    click.echo(separator)
    for row in rows:
        click.echo("  ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))


def handle_error(exc: Exception, exit_code: int = 1) -> None:
    """Stampa il messaggio dell'eccezione e termina con exit_code."""
    msg = getattr(exc, "message", str(exc))
    echo_error(msg, exit_code=exit_code)
