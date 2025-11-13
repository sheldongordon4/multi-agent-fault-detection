from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FaultTicket(BaseModel):
    ticket_id: str = Field(..., description="Unique identifier for the ticket")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    scenario_id: Optional[str] = Field(
        None, description="ID or label of the simulated fault scenario"
    )
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    root_cause: str = Field(..., description="Short description of the root cause")
    summary: str = Field(..., description="Short, human-readable summary")
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extra context such as key SCADA or relay signals used",
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Recommended next actions for the operator",
    )
    kb_citations: List[str] = Field(
        default_factory=list,
        description="References to SOPs or KB entries",
    )
