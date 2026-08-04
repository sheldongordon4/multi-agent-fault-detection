from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.orm import Base, TimeStampMixin


class FaultTicketRecord(Base, TimeStampMixin):
    """
    Persisted FaultTicket (the Persistence service, docs/System_Architecture.md §4.6).

    The primary key is the deterministic incident_id (bus_id + start_ts) so that
    re-processing the same incident overwrites rather than duplicating (idempotency,
    §7). The full validated ticket is kept verbatim in `raw` for the history API.
    """

    __tablename__ = "fault_tickets"

    incident_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scenario: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bus_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    fault_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, nullable=False)
