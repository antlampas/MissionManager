# SPDX-License-Identifier: CC-BY-SA-4.0
"""Helper di persistenza condivisi dai repository del sotto-albero obiettivi→attività."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import ActivityRow, ObjectiveRow


def delete_objective_subtree(session: Session, *objective_filters) -> None:
    """Elimina le attività e poi gli obiettivi che soddisfano ``objective_filters``.

    L'ordine — prima le attività (figlie), poi gli obiettivi (padri) — rispetta il
    vincolo FK ``activity.objective_id`` sui backend che lo applicano (MySQL/PostgreSQL).
    Usato per sostituire o cancellare il sotto-albero di una missione (blueprint) o
    di un assignment, a seconda dei filtri passati.
    """
    objective_ids = session.query(ObjectiveRow.id).filter(*objective_filters)
    session.query(ActivityRow).filter(
        ActivityRow.objective_id.in_(objective_ids)
    ).delete(synchronize_session="fetch")
    session.query(ObjectiveRow).filter(*objective_filters).delete(
        synchronize_session="fetch"
    )
