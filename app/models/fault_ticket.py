# app/models/fault_ticket.py
from pydantic import BaseModel
from typing import List, Optional

class KBCitation(BaseModel):
    source_id: str
    title: str
    section: Optional[str] = None
    url: Optional[str] = None
    snippet: Optional[str] = None

class EvidenceWindow(BaseModel):
    start_timestamp: str
    end_timestamp: str
    metric: str
    description: str

class FaultTicket(BaseModel):
    ticket_id: str
    scenario: str
    bus_id: str
    fault_type: str
    severity: str
    status: str
    summary: str
    root_cause: str
    recommended_actions: List[str]
    evidence: List[EvidenceWindow]
    kb_citations: List[KBCitation]
    created_at: str
