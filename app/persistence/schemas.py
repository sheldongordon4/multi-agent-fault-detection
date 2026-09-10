from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TicketSummary(BaseModel):
    incident_id: str
    ticket_id: str
    scenario: str | None = None
    bus_id: str | None = None
    fault_type: str | None = None
    severity: str | None = None
    status: str | None = None
    summary: str | None = None
    created_at: datetime
    # Derived from bus_id on read (app/persistence/service.py::_with_impact) so
    # the list can rank by impact without unpacking every ticket's `raw`, and so
    # a ticket diagnosed before the customer table existed still reports one.
    customers_affected: int | None = None
    customers_share: float | None = None

    model_config = {"from_attributes": True}


class TicketListResponse(BaseModel):
    items: list[TicketSummary]
    count: int


class TicketDetail(TicketSummary):
    raw: dict[str, Any]


class RepeatOffender(BaseModel):
    """A bus that has produced the same fault code more than once."""

    bus_id: str
    fault_code: str
    occurrences: int
    first_seen: datetime
    last_seen: datetime
    worst_severity: str | None = None
    customers_affected: int | None = None
    mean_days_between: float | None = None
    recent_incident_ids: list[str] = []


class RepeatOffenderResponse(BaseModel):
    items: list[RepeatOffender]
    count: int
    window_days: int
    min_occurrences: int
