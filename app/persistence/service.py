from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database import engine, fetch_all, fetch_one
from app.faults.customers import customers_affected, impact_share
from app.faults.schemas import Severity, coerce_severity
from app.persistence.models import FaultTicketRecord


async def upsert_ticket(incident_id: str, ticket: dict[str, Any]) -> None:
    """
    Insert (or overwrite) a fault ticket keyed by incident_id.

    At-least-once Kafka delivery means the same incident can be processed more than
    once; the ON CONFLICT upsert makes that idempotent (§7) instead of duplicating.
    """
    values = {
        "incident_id": incident_id,
        "ticket_id": ticket.get("ticket_id", incident_id),
        "scenario": ticket.get("scenario"),
        "bus_id": ticket.get("bus_id"),
        "fault_type": ticket.get("fault_type"),
        "severity": ticket.get("severity"),
        "status": ticket.get("status"),
        "summary": _summary_text(ticket.get("summary")),
        "raw": ticket,
    }

    stmt = pg_insert(FaultTicketRecord).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[FaultTicketRecord.incident_id],
        set_={k: v for k, v in values.items() if k != "incident_id"},
    )

    async with engine.connect() as conn:
        await conn.execute(stmt)
        await conn.commit()


async def list_tickets(
    limit: int = 50, conn: AsyncConnection | None = None
) -> list[dict[str, Any]]:
    """Most-recent fault tickets for the history API."""
    rows = await fetch_all(
        sa.select(FaultTicketRecord).order_by(FaultTicketRecord.created_at.desc()).limit(limit),
        connection=conn,
    )
    return [_with_impact(row) for row in rows]


async def get_ticket(
    incident_id: str, conn: AsyncConnection | None = None
) -> dict[str, Any] | None:
    """One fault ticket by incident_id (includes the full `raw` ticket)."""
    row = await fetch_one(
        sa.select(FaultTicketRecord).where(FaultTicketRecord.incident_id == incident_id),
        connection=conn,
    )
    return _with_impact(row) if row else None


def _with_impact(row: dict[str, Any]) -> dict[str, Any]:
    """
    Add customer impact to a ticket row on the way out.

    Derived rather than stored: the count is a property of the feeder's
    topology, not of the incident, so a ticket written before the table existed
    — or written while it held the wrong numbers — reports today's figure
    instead of the one that happened to be current when it was diagnosed.
    """
    bus_id = row.get("bus_id")
    return {
        **row,
        "customers_affected": customers_affected(bus_id),
        "customers_share": impact_share(bus_id),
    }


def _summary_text(summary: Any) -> str | None:
    """Tickets carry summary as either a string or a {text, ...} object."""
    if isinstance(summary, dict):
        return summary.get("text")
    return summary


# How severities rank when collapsing many tickets into one row. Postgres sorts
# the stored strings alphabetically, which puts "low" above "medium" — the wrong
# way round for the thing an operator scans first.
_SEVERITY_RANK = {Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}


def _worst(severities: list[Any]) -> str | None:
    """
    The most severe of a group, normalising synonyms on the way.

    Tickets are persisted with whatever severity string reached them, and the
    coordinator's vocabulary is wider than the enum: "moderate", "critical" and
    "severe" are all in the data. Ranking the raw strings scores every one of
    them as unknown, so a group containing a critical fault reported as its
    mildest member.
    """
    ranked = [coerce_severity(s) for s in severities if s]
    if not ranked:
        return None
    return str(max(ranked, key=lambda s: _SEVERITY_RANK.get(s, 0)))


async def repeat_offenders(
    days: int = 30,
    min_occurrences: int = 2,
    conn: AsyncConnection | None = None,
) -> list[dict[str, Any]]:
    """
    Buses that keep faulting the same way — the reactive-to-predictive step.

    The SOPs already say this in prose: a repeated transient SLG at one location
    often precedes a permanent failure, and a marginal connector will recur. The
    tickets to prove it have been in Postgres the whole time, one row per
    incident, with the bus and the timestamp on them. Nothing was reading them
    as a series.

    Grouped by bus AND fault code, not by bus alone. A bus with three unrelated
    faults is a busy bus; a bus with three SLGs is a defect that has not been
    found yet, and only the second is worth sending someone to inspect before it
    fails.

    The code is the leading token of `fault_type`, which the coordinator writes
    as prose ("SLG near b671 (~0.4 km)") so that the distance travels with it.
    Grouping on the whole string would put every occurrence in its own bucket,
    since the estimated distance moves between events.
    """
    since = datetime.now(UTC) - timedelta(days=days)
    code = sa.func.split_part(FaultTicketRecord.fault_type, " ", 1).label("fault_code")

    stmt = (
        sa.select(
            FaultTicketRecord.bus_id,
            code,
            sa.func.count().label("occurrences"),
            sa.func.min(FaultTicketRecord.created_at).label("first_seen"),
            sa.func.max(FaultTicketRecord.created_at).label("last_seen"),
            sa.func.array_agg(
                aggregate_order_by(
                    FaultTicketRecord.incident_id, FaultTicketRecord.created_at.desc()
                )
            ).label("incident_ids"),
            sa.func.array_agg(FaultTicketRecord.severity).label("severities"),
        )
        .where(
            FaultTicketRecord.created_at >= since,
            FaultTicketRecord.bus_id.is_not(None),
            FaultTicketRecord.fault_type.is_not(None),
        )
        .group_by(FaultTicketRecord.bus_id, code)
        .having(sa.func.count() >= min_occurrences)
        .order_by(sa.desc("occurrences"), sa.desc("last_seen"))
    )

    rows = await fetch_all(stmt, connection=conn)
    return [_shape_offender(row) for row in rows]


def _cadence_days(first_seen: Any, last_seen: Any, occurrences: int) -> float | None:
    """
    Mean gap between occurrences, over the span they actually cover.

    N incidents have N-1 gaps between them, so a pair a day apart recurs every
    one day rather than every half day. None when there is nothing to average:
    a single incident, or several stamped at the same instant (a replay).
    """
    if occurrences < 2 or first_seen is None or last_seen is None:
        return None
    span = (last_seen - first_seen).total_seconds() / 86400.0
    if span <= 0:
        return None
    return round(span / (occurrences - 1), 2)


def _shape_offender(row: dict[str, Any]) -> dict[str, Any]:
    """One grouped row into the API shape, with impact and cadence filled in."""
    worst = _worst(row.get("severities") or [])

    bus_id = row.get("bus_id")
    occurrences = int(row.get("occurrences") or 0)
    incident_ids = list(row.get("incident_ids") or [])

    return {
        "bus_id": bus_id,
        "fault_code": row.get("fault_code"),
        "occurrences": occurrences,
        "first_seen": row.get("first_seen"),
        "last_seen": row.get("last_seen"),
        "worst_severity": worst,
        "customers_affected": customers_affected(bus_id),
        # Days between recurrences, so "four in a week" reads differently from
        # "four in a month" without the caller doing the arithmetic. Measured
        # across the incidents themselves, NOT across the lookback window:
        # dividing the window reported twenty faults inside four days as one
        # every eighteen days, which is the opposite of what the operator needs
        # to know.
        "mean_days_between": _cadence_days(
            row.get("first_seen"), row.get("last_seen"), occurrences
        ),
        # Newest first, capped: this drives a link list, not an export.
        "recent_incident_ids": incident_ids[:5],
    }
