import pytest
from pydantic import ValidationError

from backend.kafka.schemas import validate_payload

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


# raw.signals carries 3-phase WAVEFORM frames, not scalar SCADA readings: I0/I1
# and I2/I1 need all three phases (Open Decision #6). See ml/waveform.py.
_VALID_FRAME = {
    "bus_id": "b671",
    "t0": 1_725_000_000.0,
    "fs": 1920.0,
    "Va": [1.0, 0.0, -1.0],
    "Vb": [0.0, -1.0, 1.0],
    "Vc": [-1.0, 1.0, 0.0],
    "Ia": [400.0, 0.0, -400.0],
    "Ib": [0.0, -400.0, 400.0],
    "Ic": [-400.0, 400.0, 0.0],
}


def test_validate_payload_accepts_topic_contracts():
    frame = validate_payload("raw.signals", _VALID_FRAME)
    assert frame["bus_id"] == "b671"
    assert frame["fs"] == 1920.0
    assert len(frame["Va"]) == 3
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

    # A frame without a sample rate cannot be expanded back into samples, so the
    # timestamps would be unrecoverable — reject it rather than guess.
    with pytest.raises(ValidationError):
        validate_payload("raw.signals", {**_VALID_FRAME, "fs": 0.0})

    with pytest.raises(ValidationError):
        validate_payload("faulttickets", {"incident_id": "missing-fields"})
