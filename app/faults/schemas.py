from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TicketStatus(StrEnum):
    DIAGNOSED = "diagnosed"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


# LLM/heuristic output is free-form-ish; map common synonyms onto the enum instead
# of rejecting the ticket. Unknown values fall back to a safe default.
_SEVERITY_SYNONYMS = {
    "info": Severity.LOW,
    "informational": Severity.LOW,
    "minor": Severity.LOW,
    "low": Severity.LOW,
    "medium": Severity.MEDIUM,
    "moderate": Severity.MEDIUM,
    "med": Severity.MEDIUM,
    "elevated": Severity.MEDIUM,
    "high": Severity.HIGH,
    "critical": Severity.HIGH,
    "severe": Severity.HIGH,
    "major": Severity.HIGH,
}


class TopBus(BaseModel):
    bus: str
    minVa: float | None = None
    maxIa: float | None = None
    maxI0I1: float | None = None
    maxI2I1: float | None = None


class DiagnoseRequest(BaseModel):
    """A detection result to diagnose (the anomalies.detected shape, manual entry)."""

    feeder: str
    incident_id: str | None = None
    severity: str | None = None
    anomaly_score: float | None = None
    top_buses: list[TopBus] = Field(default_factory=list)


class KBCitation(BaseModel):
    source_id: str
    title: str
    section: str | None = None
    url: str | None = None
    snippet: str | None = None


class EvidenceWindow(BaseModel):
    start_timestamp: str
    end_timestamp: str
    metric: str
    description: str


class FaultTicket(BaseModel):
    ticket_id: str
    scenario: str
    bus_id: str
    fault_type: str = Field(min_length=1)
    severity: Severity
    status: TicketStatus = TicketStatus.DIAGNOSED
    summary: str
    root_cause: str
    recommended_actions: list[str]
    evidence: list[EvidenceWindow]
    kb_citations: list[KBCitation]
    created_at: str

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_severity(cls, v: object) -> Severity:
        if isinstance(v, Severity):
            return v
        return _SEVERITY_SYNONYMS.get(str(v).strip().lower(), Severity.MEDIUM)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: object) -> TicketStatus:
        if isinstance(v, TicketStatus):
            return v
        try:
            return TicketStatus(str(v).strip().lower())
        except ValueError:
            return TicketStatus.DIAGNOSED
