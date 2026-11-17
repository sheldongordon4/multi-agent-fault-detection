"""
Assignment service — who owns a fault ticket and what state the work is in.

THE INVARIANT THIS MODULE EXISTS TO PROTECT
-------------------------------------------
Assignment state is kept in `ticket_assignments`, never on `fault_tickets`.
`backend/persistence/service.py::upsert_ticket` writes ON CONFLICT DO UPDATE across
every ticket column, and Kafka delivery is at-least-once, so a redelivery
(consumer rebalance, pod restart, DLQ replay) rewrites the ticket row wholesale.
Anything an operator had set there would be silently reset, with nothing in the
logs to explain it. Nothing under `backend/kafka/` writes to the tables in this
module, so redelivery is harmless.

The assignment row is created lazily on the first write. Reads LEFT JOIN from
`fault_tickets`, so a missing row simply *means* unassigned — no back-fill is
needed for tickets that predate this feature.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.assignments.constants import (
    DEFAULT_PRIORITY,
    DEFAULT_SLA_MINUTES,
    PRIORITY_BY_SEVERITY,
    SLA_MINUTES_BY_SEVERITY,
    TERMINAL_STATES,
    EventKind,
    Priority,
    WorkState,
)
from backend.assignments.models import AssignmentEvent, Operator, TicketAssignment
from backend.assignments.schemas import AssignmentUpdate
from backend.database import engine, fetch_all, fetch_one
from backend.persistence.models import FaultTicketRecord

# Mirrors _SEVERITY_SYNONYMS in backend/faults/schemas.py. The persisted column holds
# the coordinator's raw string, so "critical" and "moderate" really do come back
# from the database.
_SEVERITY_SYNONYMS = {
    "info": "low",
    "informational": "low",
    "minor": "low",
    "low": "low",
    "medium": "medium",
    "moderate": "medium",
    "med": "medium",
    "elevated": "medium",
    "high": "high",
    "critical": "high",
    "severe": "high",
    "major": "high",
}


def normalize_severity(value: str | None) -> str:
    return _SEVERITY_SYNONYMS.get((value or "").strip().lower(), "medium")


def default_priority(severity: str | None) -> Priority:
    return PRIORITY_BY_SEVERITY.get(normalize_severity(severity), DEFAULT_PRIORITY)


def default_due_at(severity: str | None, *, since: datetime | None = None) -> datetime:
    minutes = SLA_MINUTES_BY_SEVERITY.get(normalize_severity(severity), DEFAULT_SLA_MINUTES)
    return (since or datetime.now(UTC)) + timedelta(minutes=minutes)


class StaleAssignmentVersion(Exception):
    """Raised when `expected_version` does not match the stored row (-> HTTP 409)."""

    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__(f"assignment has moved on (current version {current_version})")


# ── operators ────────────────────────────────────────────────────────────────


async def list_operators(
    *, include_inactive: bool = False, conn: AsyncConnection | None = None
) -> list[dict[str, Any]]:
    """
    The roster, with each operator's open-ticket count.

    The count is aggregated in the database rather than by fetching every
    assignment and counting in Python — one query regardless of roster size.
    """
    open_counts = (
        sa.select(
            TicketAssignment.assignee_id.label("assignee_id"),
            sa.func.count().label("open_count"),
        )
        .where(TicketAssignment.work_state.notin_([s.value for s in TERMINAL_STATES]))
        .where(TicketAssignment.assignee_id.is_not(None))
        .group_by(TicketAssignment.assignee_id)
        .subquery()
    )

    query = (
        sa.select(
            Operator,
            sa.func.coalesce(open_counts.c.open_count, 0).label("open_count"),
        )
        .select_from(Operator)
        .outerjoin(open_counts, open_counts.c.assignee_id == Operator.id)
        .order_by(Operator.on_shift.desc(), Operator.name.asc())
    )

    if not include_inactive:
        query = query.where(Operator.active.is_(True))

    return await fetch_all(query, connection=conn)


async def get_operator(
    operator_id: str, conn: AsyncConnection | None = None
) -> dict[str, Any] | None:
    return await fetch_one(sa.select(Operator).where(Operator.id == operator_id), connection=conn)


async def create_operator(values: dict[str, Any]) -> dict[str, Any]:
    async with engine.connect() as conn:
        row = await fetch_one(
            sa.insert(Operator).values(**values).returning(Operator),
            connection=conn,
            commit_after=True,
        )
    return {**(row or {}), "open_count": 0}


async def update_operator(operator_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
    if not values:
        return await get_operator(operator_id)

    async with engine.connect() as conn:
        return await fetch_one(
            sa.update(Operator)
            .where(Operator.id == operator_id)
            .values(**values)
            .returning(Operator),
            connection=conn,
            commit_after=True,
        )


# ── assignments ──────────────────────────────────────────────────────────────

# Everything above `work_state` projects the ticket; everything from it down
# comes from the (possibly absent) assignment row.
_ASSIGNMENT_SELECT = (
    sa.select(
        FaultTicketRecord.incident_id,
        FaultTicketRecord.ticket_id,
        FaultTicketRecord.bus_id,
        FaultTicketRecord.scenario,
        FaultTicketRecord.fault_type,
        FaultTicketRecord.severity,
        FaultTicketRecord.status,
        FaultTicketRecord.summary,
        FaultTicketRecord.created_at,
        TicketAssignment.work_state,
        TicketAssignment.priority,
        TicketAssignment.assignee_id,
        TicketAssignment.due_at,
        TicketAssignment.note,
        TicketAssignment.version,
        TicketAssignment.updated_at,
        Operator.name.label("assignee_name"),
        Operator.initials.label("assignee_initials"),
    )
    .select_from(FaultTicketRecord)
    .outerjoin(
        TicketAssignment,
        TicketAssignment.incident_id == FaultTicketRecord.incident_id,
    )
    .outerjoin(Operator, Operator.id == TicketAssignment.assignee_id)
)

# An absent row is unassigned, so a state filter has to see through the join.
_EFFECTIVE_STATE = sa.func.coalesce(TicketAssignment.work_state, WorkState.UNASSIGNED.value)

# Same for priority, and it costs more here: a ticket with no assignment row is
# still *displayed* with a severity-derived priority (see _project), so filtering
# on the raw column alone would hide exactly the urgent unassigned work the
# filter exists to surface. This CASE mirrors default_priority() in SQL.
_SEVERITY_TO_PRIORITY_SQL = sa.case(
    {
        synonym: PRIORITY_BY_SEVERITY[level].value
        for synonym, level in _SEVERITY_SYNONYMS.items()
        if level in PRIORITY_BY_SEVERITY
    },
    value=sa.func.lower(sa.func.trim(FaultTicketRecord.severity)),
    else_=DEFAULT_PRIORITY.value,
)

_EFFECTIVE_PRIORITY = sa.func.coalesce(TicketAssignment.priority, _SEVERITY_TO_PRIORITY_SQL)


def _project(row: dict[str, Any]) -> dict[str, Any]:
    """
    Fill the LEFT JOIN's NULL side with the defaults an unwritten assignment row
    would have had, so the client never special-cases a missing row.
    """
    severity = row.get("severity")
    return {
        **row,
        "work_state": row.get("work_state") or WorkState.UNASSIGNED.value,
        "priority": row.get("priority") or default_priority(severity).value,
        "version": row.get("version") or 0,
    }


async def list_assignments(
    *,
    work_state: str | None = None,
    assignee_id: str | None = None,
    unassigned_only: bool = False,
    severity: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
    conn: AsyncConnection | None = None,
) -> list[dict[str, Any]]:
    """Tickets joined to their assignment, newest first. Filtering happens in SQL."""
    query = _ASSIGNMENT_SELECT

    if work_state:
        query = query.where(_EFFECTIVE_STATE == work_state)

    if unassigned_only:
        query = query.where(TicketAssignment.assignee_id.is_(None))
    elif assignee_id:
        query = query.where(TicketAssignment.assignee_id == assignee_id)

    if severity:
        # Match every synonym that normalizes to the requested level, because the
        # column stores the coordinator's raw string.
        synonyms = [k for k, v in _SEVERITY_SYNONYMS.items() if v == severity]
        query = query.where(sa.func.lower(FaultTicketRecord.severity).in_(synonyms))

    if priority:
        query = query.where(_EFFECTIVE_PRIORITY == priority)

    if search:
        needle = f"%{search.strip().lower()}%"
        query = query.where(
            sa.or_(
                sa.func.lower(FaultTicketRecord.incident_id).like(needle),
                sa.func.lower(FaultTicketRecord.ticket_id).like(needle),
                sa.func.lower(FaultTicketRecord.bus_id).like(needle),
                sa.func.lower(FaultTicketRecord.fault_type).like(needle),
                sa.func.lower(FaultTicketRecord.summary).like(needle),
            )
        )

    query = query.order_by(FaultTicketRecord.created_at.desc()).limit(limit).offset(offset)

    rows = await fetch_all(query, connection=conn)
    return [_project(row) for row in rows]


async def get_assignment(
    incident_id: str, conn: AsyncConnection | None = None
) -> dict[str, Any] | None:
    row = await fetch_one(
        _ASSIGNMENT_SELECT.where(FaultTicketRecord.incident_id == incident_id),
        connection=conn,
    )
    return _project(row) if row else None


async def update_assignment(
    incident_id: str,
    patch: AssignmentUpdate,
    *,
    actor_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Apply a partial update and append the matching activity events.

    Returns None when the incident has no ticket. The row write and its events go
    in one transaction, so the feed can never disagree with the row it describes.
    """
    changed = patch.model_fields_set

    async with engine.begin() as conn:
        ticket = await fetch_one(
            sa.select(
                FaultTicketRecord.incident_id,
                FaultTicketRecord.severity,
                FaultTicketRecord.created_at,
            ).where(FaultTicketRecord.incident_id == incident_id),
            connection=conn,
        )
        if ticket is None:
            return None

        # FOR UPDATE so two concurrent assignments serialise instead of racing.
        current = await fetch_one(
            sa.select(TicketAssignment)
            .where(TicketAssignment.incident_id == incident_id)
            .with_for_update(),
            connection=conn,
        )

        severity = ticket["severity"]
        if current is None:
            # The defaults the row would have had, so the diff below is honest
            # about what actually changed on the first write.
            current = {
                "assignee_id": None,
                "work_state": WorkState.UNASSIGNED.value,
                "priority": default_priority(severity).value,
                "due_at": default_due_at(severity, since=ticket["created_at"]),
                "note": None,
                "version": 0,
            }

        if patch.expected_version is not None and patch.expected_version != current["version"]:
            raise StaleAssignmentVersion(current["version"])

        values: dict[str, Any] = {
            "assignee_id": current["assignee_id"],
            "work_state": current["work_state"],
            "priority": current["priority"],
            "due_at": current["due_at"],
            "note": current["note"],
        }
        events: list[dict[str, Any]] = []

        if "assignee_id" in changed and patch.assignee_id != current["assignee_id"]:
            values["assignee_id"] = patch.assignee_id
            events.append(
                {
                    "kind": (
                        EventKind.ASSIGNED if patch.assignee_id else EventKind.UNASSIGNED
                    ).value,
                    "from_value": current["assignee_id"],
                    "to_value": patch.assignee_id,
                }
            )

            # Assigning an untouched ticket implies it is now someone's work, and
            # dropping it implies it is nobody's — but only when the same request
            # did not say otherwise.
            if "work_state" not in changed:
                if patch.assignee_id and current["work_state"] == WorkState.UNASSIGNED.value:
                    values["work_state"] = WorkState.ASSIGNED.value
                elif not patch.assignee_id and current["work_state"] == WorkState.ASSIGNED.value:
                    values["work_state"] = WorkState.UNASSIGNED.value

                if values["work_state"] != current["work_state"]:
                    events.append(
                        {
                            "kind": EventKind.STATE_CHANGED.value,
                            "from_value": current["work_state"],
                            "to_value": values["work_state"],
                        }
                    )

        if (
            "work_state" in changed
            and patch.work_state is not None
            and patch.work_state.value != current["work_state"]
        ):
            values["work_state"] = patch.work_state.value
            events.append(
                {
                    "kind": EventKind.STATE_CHANGED.value,
                    "from_value": current["work_state"],
                    "to_value": patch.work_state.value,
                }
            )

        if (
            "priority" in changed
            and patch.priority is not None
            and patch.priority.value != current["priority"]
        ):
            values["priority"] = patch.priority.value
            events.append(
                {
                    "kind": EventKind.PRIORITY_CHANGED.value,
                    "from_value": current["priority"],
                    "to_value": patch.priority.value,
                }
            )

        if "due_at" in changed and patch.due_at != current["due_at"]:
            values["due_at"] = patch.due_at
            events.append(
                {
                    "kind": EventKind.DUE_CHANGED.value,
                    "from_value": _iso(current["due_at"]),
                    "to_value": _iso(patch.due_at),
                }
            )

        if "note" in changed and patch.note != current["note"]:
            values["note"] = patch.note
            events.append({"kind": EventKind.NOTE_CHANGED.value, "body": patch.note})

        # A no-op PATCH still returns the row, but must not bump the version or
        # write a misleading event.
        if events:
            await _upsert(conn, incident_id, values, from_version=current["version"])
            await _append_events(conn, incident_id, actor_id, events)

    return await get_assignment(incident_id)


async def add_comment(
    incident_id: str, body: str, *, actor_id: str | None = None
) -> dict[str, Any] | None:
    """Append a comment. Deliberately does not create or touch the assignment row."""
    async with engine.begin() as conn:
        exists = await fetch_one(
            sa.select(FaultTicketRecord.incident_id).where(
                FaultTicketRecord.incident_id == incident_id
            ),
            connection=conn,
        )
        if exists is None:
            return None

        rows = await _append_events(
            conn, incident_id, actor_id, [{"kind": EventKind.COMMENTED.value, "body": body}]
        )

    return rows[0] if rows else None


async def list_events(
    incident_id: str, conn: AsyncConnection | None = None
) -> list[dict[str, Any]]:
    """The activity feed for one incident, oldest first."""
    return await fetch_all(
        sa.select(AssignmentEvent, Operator.name.label("actor_name"))
        .select_from(AssignmentEvent)
        .outerjoin(Operator, Operator.id == AssignmentEvent.actor_id)
        .where(AssignmentEvent.incident_id == incident_id)
        .order_by(AssignmentEvent.created_at.asc(), AssignmentEvent.id.asc()),
        connection=conn,
    )


# ── internals ────────────────────────────────────────────────────────────────


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


async def _upsert(
    conn: AsyncConnection,
    incident_id: str,
    values: dict[str, Any],
    *,
    from_version: int,
) -> None:
    """
    Write the row, but only if it still holds `from_version`.

    The version guard lives on the conflict clause rather than relying on the
    caller's earlier SELECT ... FOR UPDATE, because that SELECT locks nothing
    when the row does not exist yet: two operators claiming the same untouched
    ticket would both read version 0, both pass the check, and the second would
    silently overwrite the first. Here the loser's DO UPDATE matches no row and
    is reported as the conflict it is.
    """
    payload = {**values, "incident_id": incident_id, "version": from_version + 1}
    stmt = pg_insert(TicketAssignment).values(**payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=[TicketAssignment.incident_id],
        set_={k: v for k, v in payload.items() if k != "incident_id"},
        where=TicketAssignment.version == from_version,
    )
    result = await conn.execute(stmt)

    if result.rowcount == 0:
        current = await fetch_one(
            sa.select(TicketAssignment.version).where(TicketAssignment.incident_id == incident_id),
            connection=conn,
        )
        raise StaleAssignmentVersion(current["version"] if current else from_version)


async def _append_events(
    conn: AsyncConnection,
    incident_id: str,
    actor_id: str | None,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        result = await conn.execute(
            sa.insert(AssignmentEvent)
            .values(
                incident_id=incident_id,
                actor_id=actor_id,
                kind=event["kind"],
                from_value=event.get("from_value"),
                to_value=event.get("to_value"),
                body=event.get("body"),
            )
            .returning(AssignmentEvent)
        )
        row = result.first()
        if row is not None:
            rows.append(row._asdict())
    return rows
