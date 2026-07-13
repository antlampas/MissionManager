# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ...domain.entities import Activity, Mission, Objective
from ...domain.exceptions import NotFoundError
from ...infrastructure.base import RepositoryAdapter
from .models import ActivityRow, AssignmentRow, MissionRow, ObjectiveRow
from ._cascade import delete_objective_subtree
from ._mappers import (
    activity_from_row,
    mission_from_row,
    mission_to_row,
    objective_from_row,
)


class SqlAlchemyMissionRepository(RepositoryAdapter[Mission]):

    def __init__(self, session: Session) -> None:
        self._s = session

    def _load_objectives(self, mission_id: UUID) -> list[Objective]:
        obj_rows = (
            self._s.query(ObjectiveRow)
            .filter(
                ObjectiveRow.mission_id == mission_id,
                ObjectiveRow.assignment_id.is_(None),
            )
            .all()
        )
        result = []
        for obj_row in obj_rows:
            act_rows = (
                self._s.query(ActivityRow)
                .filter(ActivityRow.objective_id == obj_row.id)
                .all()
            )
            activities = [activity_from_row(r) for r in act_rows]
            result.append(objective_from_row(obj_row, activities))
        return result

    def get(self, id: UUID) -> Mission:
        row = self._s.get(MissionRow, id)
        if row is None:
            raise NotFoundError(f"Mission {id} non trovata", resource_type="mission", resource_id=id)
        objectives = self._load_objectives(id)
        return mission_from_row(row, objectives)

    def get_for_update(self, id: UUID) -> Mission:
        """Blocca la missione durante il controllo e la modifica delle policy.

        PostgreSQL e MySQL applicano il lock; SQLite lo ignora ma conserva il
        comportamento funzionale utile alla suite locale.
        """
        row = (
            self._s.query(MissionRow)
            .filter(MissionRow.id == id)
            .with_for_update()
            .one_or_none()
        )
        if row is None:
            raise NotFoundError(
                f"Mission {id} non trovata", resource_type="mission", resource_id=id
            )
        return mission_from_row(row, self._load_objectives(id))

    def list(self, filters: dict) -> list[Mission]:
        query = self._s.query(MissionRow)
        title = filters.get("title")
        if title:
            query = query.filter(MissionRow.title.contains(str(title)))
        rows = query.all()
        result = []
        for row in rows:
            objectives = self._load_objectives(row.id)
            result.append(mission_from_row(row, objectives))
        return result

    def save(self, entity: Mission) -> Mission:
        existing = self._s.get(MissionRow, entity.id)
        row = mission_to_row(entity, existing)
        if existing is None:
            self._s.add(row)

        # Replace blueprint objectives
        delete_objective_subtree(
            self._s,
            ObjectiveRow.mission_id == entity.id,
            ObjectiveRow.assignment_id.is_(None),
        )

        # Inserisci prima tutti gli obiettivi, poi le attività. Tra ObjectiveRow
        # e ActivityRow non esiste una relationship(): la unit-of-work di
        # SQLAlchemy non deduce dalla sola FK activity.objective_id che
        # l'obiettivo vada inserito per primo e può emettere l'INSERT delle
        # attività prima di quello dell'obiettivo. Su backend che applicano i
        # vincoli (MySQL/PostgreSQL) questo fa fallire l'INSERT con un errore di
        # foreign key; il flush intermedio garantisce l'ordine corretto.
        for obj in entity.objectives:
            obj_row = ObjectiveRow(
                id=obj.id,
                description=obj.description,
                mission_id=entity.id,
                assignment_id=None,
            )
            self._s.add(obj_row)
        self._s.flush()

        for obj in entity.objectives:
            for act in obj.activities:
                act_row = ActivityRow(
                    id=act.id,
                    title=act.title,
                    description=act.description,
                    status=act.status.value,
                    objective_id=obj.id,
                    assignees=[str(a) for a in act.assignees],
                )
                self._s.add(act_row)

        self._s.flush()
        return entity

    def delete(self, id: UUID) -> bool:
        row = self._s.get(MissionRow, id)
        if row is None:
            return False

        # Raccoglie assignment IDs prima di eliminarli
        assignment_ids = [
            r[0] for r in self._s.query(AssignmentRow.id)
            .filter(AssignmentRow.mission_id == id)
            .all()
        ]
        if assignment_ids:
            # Obiettivi e attività degli assignment, poi gli assignment stessi
            delete_objective_subtree(
                self._s, ObjectiveRow.assignment_id.in_(assignment_ids)
            )
            self._s.query(AssignmentRow).filter(
                AssignmentRow.mission_id == id
            ).delete(synchronize_session="fetch")

        # Obiettivi e attività del blueprint
        delete_objective_subtree(
            self._s,
            ObjectiveRow.mission_id == id,
            ObjectiveRow.assignment_id.is_(None),
        )
        self._s.delete(row)
        self._s.flush()
        return True

    def exists(self, id: UUID) -> bool:
        return self._s.get(MissionRow, id) is not None

    def get_by_title(self, title: str) -> Optional[Mission]:
        row = self._s.query(MissionRow).filter(MissionRow.title == title).first()
        if row is None:
            return None
        return mission_from_row(row, self._load_objectives(row.id))
