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

    model_config = {"from_attributes": True}


class TicketListResponse(BaseModel):
    items: list[TicketSummary]
    count: int


class TicketDetail(TicketSummary):
    raw: dict[str, Any]
