import pytest
from pydantic import ValidationError

from app.kafka.schemas import validate_payload

_VALID_TICKET = {
    "ticket_id": "T-1",
    "incident_id": "ieee13:evt-1",
    "scenario": "feeder:ieee13",
    "bus_id": "b671",
    "fault_type": "Ground fault",
    "severity": "high",
    "summary": "Fault detected.",
    "root_cause": "Sequence imbalance.",
    "recommended_actions": ["Inspect relay records"],
    "evidence": [],
    "kb_citations": [],
    "created_at": "2026-08-28T00:00:00Z",
}


def test_validate_payload_accepts_topic_contracts():
    assert validate_payload("raw.signals", {"bus_id": "b1", "value": 1})["bus_id"] == "b1"
    assert validate_payload(
        "feeder.events",
        {"feeder": "ieee13", "timestamp": "now", "features": {"min_Va": 0.9}},
    )["feeder"] == "ieee13"
    assert validate_payload(
        "anomalies.detected",
        {"feeder": "ieee13", "verdict": {"isFault": True}},
    )["feeder"] == "ieee13"
    assert validate_payload("faulttickets", _VALID_TICKET)["incident_id"] == "ieee13:evt-1"


def test_validate_payload_rejects_invalid_payload():
    with pytest.raises(ValidationError):
        validate_payload("raw.signals", {"value": 1})

    with pytest.raises(ValidationError):
        validate_payload("faulttickets", {"incident_id": "missing-fields"})
