# SPDX-License-Identifier: CC-BY-SA-4.0
"""Helper condiviso dagli handler Web per i menu di cambio stato.

Le pagine di dettaglio espongono solo le transizioni *valide* a partire dallo
stato corrente (vedi ``Status.can_transition_to``); le regole aggiuntive
specifiche di Activity/Assignment restano validate lato service, che risponde
con un errore leggibile in caso di transizione non ammessa.
"""
from __future__ import annotations

from ....domain.enums import Status


def next_statuses(current: str) -> list[str]:
    """Stati raggiungibili da ``current`` secondo la macchina a stati di dominio.

    ``UNASSIGNED`` è escluso: non è mai impostabile via update_status (la
    policy lo consente solo rimuovendo l'ultimo assegnatario), quindi non va
    offerto nel menu di cambio stato.
    """
    try:
        cur = Status(current)
    except ValueError:
        return []
    return [
        s.value
        for s in Status
        if s is not Status.UNASSIGNED and cur.can_transition_to(s)
    ]
