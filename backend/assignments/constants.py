from enum import StrEnum


class OperatorRole(StrEnum):
    CONTROL_ROOM = "control_room"
    FIELD_CREW = "field_crew"
    PROTECTION_ENG = "protection_eng"
    SUPERVISOR = "supervisor"


class WorkState(StrEnum):
    """
    The operator-owned workflow state.

    Deliberately NOT the same thing as `FaultTicket.status` (diagnosed /
    acknowledged / resolved), which is produced by the coordinator and owned by
    the pipeline. Merging them would let a redelivered ticket overwrite an
    operator's decision — see the module docstring in service.py.
    """

    UNASSIGNED = "unassigned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Priority(StrEnum):
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"
    P4 = "p4"


class EventKind(StrEnum):
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    STATE_CHANGED = "state_changed"
    PRIORITY_CHANGED = "priority_changed"
    DUE_CHANGED = "due_changed"
    NOTE_CHANGED = "note_changed"
    COMMENTED = "commented"


# Severity → default priority and SLA budget. Operators can override both; these
# only seed the assignment row the first time it is written.
PRIORITY_BY_SEVERITY: dict[str, Priority] = {
    "high": Priority.P1,
    "medium": Priority.P2,
    "low": Priority.P3,
}

SLA_MINUTES_BY_SEVERITY: dict[str, int] = {
    "high": 30,
    "medium": 120,
    "low": 480,
}

DEFAULT_PRIORITY = Priority.P3
DEFAULT_SLA_MINUTES = 480

# States that no longer count against an operator's open workload.
TERMINAL_STATES: frozenset[WorkState] = frozenset({WorkState.RESOLVED, WorkState.CLOSED})
