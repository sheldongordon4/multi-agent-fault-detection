from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.assignments.constants import (
    DEFAULT_PRIORITY,
    EventKind,
    OperatorRole,
    Priority,
    WorkState,
)
from backend.orm import Base, TimeStampMixin, ULIDMixin


class Operator(Base, ULIDMixin, TimeStampMixin):
    """
    A control-room / field operator who can own a fault ticket.

    A roster entry, NOT a user account: MAFD has no auth (see AGENTS.md), so
    there is no password, no session and no per-user scoping anywhere. The
    console picks who it is "acting as" and sends the id in `X-Actor-Id`, which
    makes the activity log *attributed* rather than *authenticated*. Anyone at
    the terminal can claim to be anyone — fine for coordinating a shift, and not
    an audit trail. Real identity would be SSO against the utility's directory,
    which is a separate decision.
    """

    __tablename__ = "operators"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    initials: Mapped[str] = mapped_column(String(4), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=OperatorRole.CONTROL_ROOM)
    # Joins the parish shading already on the map (frontend/public/map).
    parish: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Soft WIP ceiling — drives the workload bars, never enforced server-side.
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    on_shift: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class TicketAssignment(Base, TimeStampMixin):
    """
    Who owns an incident and what state the work is in — one row per incident.

    Keyed by `incident_id` to match `fault_tickets`, but kept in a SEPARATE table
    on purpose: `backend/persistence/service.py::upsert_ticket` writes
    `ON CONFLICT DO UPDATE` across every ticket column, and Kafka delivery is
    at-least-once, so anything stored on `fault_tickets` is silently reset on the
    next redelivery (rebalance, restart, DLQ replay). Nothing in `backend/kafka/`
    writes to this table.

    A row is created lazily on the first write. The board reads tickets with a
    LEFT JOIN, so "no row" simply means unassigned and nothing has to be
    back-filled for tickets that predate the feature.
    """

    __tablename__ = "ticket_assignments"

    incident_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("fault_tickets.incident_id", ondelete="CASCADE"),
        primary_key=True,
    )
    assignee_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("operators.id", ondelete="SET NULL"), nullable=True, index=True
    )
    work_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=WorkState.UNASSIGNED, index=True
    )
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default=DEFAULT_PRIORITY)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optimistic concurrency. Two operators assigning the same ticket at once
    # would otherwise last-write-wins, and dispatch two crews to one fault.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<TicketAssignment {self.incident_id} {self.work_state} {self.assignee_id}>"


class AssignmentEvent(Base, ULIDMixin):
    """
    Append-only activity log for one incident.

    Comments live here too (`kind='commented'`, text in `body`) rather than in
    their own table, so the panel renders one chronological feed without merging
    two sources client-side.
    """

    __tablename__ = "assignment_events"

    incident_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # NULL actor = the system (e.g. the row seeded from the coordinator's ticket).
    actor_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("operators.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # No TimeStampMixin: the log is append-only, so `updated_at` would be a lie.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


__all__ = [
    "AssignmentEvent",
    "EventKind",
    "Operator",
    "OperatorRole",
    "Priority",
    "TicketAssignment",
    "WorkState",
]
