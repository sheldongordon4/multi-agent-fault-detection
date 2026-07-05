from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database import engine, fetch_all, fetch_one
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
    return await fetch_all(
        sa.select(FaultTicketRecord).order_by(FaultTicketRecord.created_at.desc()).limit(limit),
        connection=conn,
    )


async def get_ticket(
    incident_id: str, conn: AsyncConnection | None = None
) -> dict[str, Any] | None:
    """One fault ticket by incident_id (includes the full `raw` ticket)."""
    return await fetch_one(
        sa.select(FaultTicketRecord).where(FaultTicketRecord.incident_id == incident_id),
        connection=conn,
    )


def _summary_text(summary: Any) -> str | None:
    """Tickets carry summary as either a string or a {text, ...} object."""
    if isinstance(summary, dict):
        return summary.get("text")
    return summary
