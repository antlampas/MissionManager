# SPDX-License-Identifier: CC-BY-SA-4.0
"""Regole di dominio esplicite (policy objects).

Separano le invarianti di dominio dai servizi applicativi.
Ogni policy è una classe stateless con un metodo validate() che solleva
l'eccezione appropriata se la regola viene violata.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from .enums import AssigneeType, Status
from .exceptions import StatusTransitionError, ValidationError

# Le invarianti del sistema ACL (INV-1..INV-5) vivono in ``domain.acl``
# (AclEntry.validate), accanto al modello che vincolano.


class AssignmentStatusPolicy:
    """Valida le transizioni di stato per MissionAssignment e Activity.

    La mappa delle transizioni ammesse è la fonte di verità; Status.can_transition_to()
    la usa internamente.  Questa policy espone la stessa logica come oggetto
    standalone, rendibile testabile e iniettabile indipendentemente.
    """

    def validate_transition(self, current: Status, requested: Status) -> None:
        """Solleva StatusTransitionError se la transizione non è ammessa."""
        if requested == Status.UNASSIGNED:
            raise ValidationError(
                "UNASSIGNED può essere ripristinato solo rimuovendo l'ultimo assegnatario",
                field="status",
            )
        if not current.can_transition_to(requested):
            raise StatusTransitionError(
                f"Transizione non consentita: {current.value} → {requested.value}",
                current_status=current.value,
                requested_status=requested.value,
            )

    def validate_activity_in_progress(self, status: Status, assignees: list) -> None:
        """Un'attività può passare a IN_PROGRESS solo se ha almeno un assegnatario."""
        if status == Status.IN_PROGRESS and not assignees:
            raise ValidationError(
                "Un'attività deve avere almeno un assegnatario per passare a IN_PROGRESS",
                field="assignees",
            )

    def validate_assignment_completion(self, outcome: Optional[str]) -> None:
        """Un assignment può essere COMPLETED solo se tutte le attività lo sono.

        Un risultato FAILED non è una variante di COMPLETED: il chiamante deve
        portare l'assignment a FAILED, così stato ed esito aggregato rimangono
        coerenti.
        """
        if outcome == "FAILED":
            raise ValidationError(
                "L'assignment contiene attività fallite e deve diventare FAILED",
                field="status",
            )
        if outcome != "COMPLETED":
            raise ValidationError(
                "L'assignment può essere COMPLETED solo quando tutte le attività sono COMPLETED",
                field="status",
            )

    def validate_activity_unassign(self, status: Status) -> None:
        if status == Status.IN_PROGRESS or status.is_terminal():
            raise ValidationError(
                "Non è possibile rimuovere assegnatari dopo l'inizio dell'attività",
                field="status",
            )


class BadgeAwardPolicy:
    """Valida le regole di assegnazione badge.

    I badge possono essere assegnati esclusivamente a MissionAssignment e
    Activity con stato COMPLETED.  Applicare un badge a target non completati
    è un errore di dominio, non di validazione dell'input.
    """

    def validate_target_completed(self, target_type: str, status: Status) -> None:
        if status != Status.COMPLETED:
            raise ValidationError(
                f"Il badge può essere assegnato solo a {target_type} con stato COMPLETED "
                f"(stato corrente: {status.value})"
            )

    def validate_no_duplicate_award(
        self, target_type: str, target_id: str, already_awarded: bool
    ) -> None:
        if already_awarded:
            raise ValidationError(
                f"Esiste già un BadgeAward per {target_type} {target_id}"
            )


class ActivityAssignmentPolicy:
    """Valida che l'assegnatario di un'attività rispetti la policy dell'assignment padre.

    Un'attività appartenente a un GROUP-assignment può essere assegnata solo
    a persone che sono membri del gruppo.  Per PERSON-assignment, solo
    l'assegnatario nominale è ammesso.
    """

    def validate_person_in_assignment(
        self,
        person_id: UUID,
        assignee_type: Optional[AssigneeType],
        assignee_id: Optional[UUID],
        members: list[UUID],
    ) -> None:
        if assignee_type == AssigneeType.GROUP:
            if person_id not in members:
                raise ValidationError(
                    f"La persona {person_id} non è membro del gruppo "
                    "assegnato all'assignment",
                    field="person_id",
                )
        elif assignee_type == AssigneeType.PERSON:
            if person_id != assignee_id:
                raise ValidationError(
                    f"La persona {person_id} non corrisponde all'assegnatario "
                    "nominale dell'assignment",
                    field="person_id",
                )
