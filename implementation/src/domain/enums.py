# SPDX-License-Identifier: CC-BY-SA-4.0
from enum import Enum

_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "UNASSIGNED": {"ASSIGNED"},
    # Un'Activity può tornare non assegnata solo prima che il lavoro inizi.
    # La transizione è usata da ActivityService.unassign() quando viene rimosso
    # l'ultimo assegnatario.
    "ASSIGNED": {"UNASSIGNED", "IN_PROGRESS", "FAILED"},
    "IN_PROGRESS": {"COMPLETED", "FAILED"},
    "COMPLETED": set(),
    "FAILED": set(),
}


class Status(Enum):
    UNASSIGNED = "UNASSIGNED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    def can_transition_to(self, target: "Status") -> bool:
        return target.value in _STATUS_TRANSITIONS.get(self.value, set())

    def is_terminal(self) -> bool:
        return self in (Status.COMPLETED, Status.FAILED)


class AssigneeType(Enum):
    PERSON = "PERSON"
    GROUP = "GROUP"


class ZoneType(Enum):
    GEOGRAPHIC = "GEOGRAPHIC"
    VIRTUAL = "VIRTUAL"


class ResourceType(Enum):
    """Tipi di risorsa del sistema ACL (DESIGN §10).

    ``SYSTEM`` identifica la risorsa sentinella ``SYSTEM:global`` per le
    operazioni non legate a una risorsa specifica.
    """

    SYSTEM = "SYSTEM"
    MISSION = "MISSION"
    ASSIGNMENT = "ASSIGNMENT"
    OBJECTIVE = "OBJECTIVE"
    ACTIVITY = "ACTIVITY"
    BADGE = "BADGE"
    PERSON = "PERSON"
    GROUP = "GROUP"
