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


def coerce_severity(value: object) -> Severity:
    """
    Map a free-form severity onto the enum.

    Shared with the persistence layer, which ranks severities read back out of
    the database and meets the same vocabulary: what the coordinator writes is
    wider than the three enum values, and normalising in one place keeps a
    "critical" from scoring as unknown in one caller and as high in another.
    """
    if isinstance(value, Severity):
        return value
    return _SEVERITY_SYNONYMS.get(str(value).strip().lower(), Severity.MEDIUM)


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


class ClassifierAlternative(BaseModel):
    """A class the classifier nearly chose instead."""

    fault_type: str
    confidence: float


class FeatureAttribution(BaseModel):
    """One measurement that put the event outside the normal distribution."""

    feature: str
    bus: str
    family: str
    label: str
    meaning: str
    value: float
    baseline: float
    sigma: float
    direction: str


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

    # ── Deterministic enrichment ─────────────────────────────────────────────
    #
    # Everything below is written by app/faults/service.py AFTER the ticket is
    # validated, from the detection payload — never by the LLM, and never
    # parsed out of its output. A confidence the model invents is worse than no
    # confidence at all, and a customer count it invents is a number an
    # operator would dispatch on. All optional: a ticket built before these
    # existed, or one whose detection carried none of it, still validates.
    fault_type_confidence: float | None = None
    fault_type_alternatives: list[ClassifierAlternative] = Field(default_factory=list)
    attribution: list[FeatureAttribution] = Field(default_factory=list)
    customers_affected: int | None = None
    customers_share: float | None = None

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_severity(cls, v: object) -> Severity:
        return coerce_severity(v)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: object) -> TicketStatus:
        if isinstance(v, TicketStatus):
            return v
        try:
            return TicketStatus(str(v).strip().lower())
        except ValueError:
            return TicketStatus.DIAGNOSED
