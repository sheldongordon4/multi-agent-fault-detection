"""Pydantic contracts for messages crossing Kafka service boundaries."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.faults.schemas import FaultTicket


class KafkaPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class RawSignal(KafkaPayload):
    """
    One cycle of 3-phase waveform for one bus (see app/ml/waveform.py).

    Replaces the old single-magnitude SCADA reading: sequence ratios (I0/I1,
    I2/I1) need all three phases, so a scalar `current_a` could never feed
    detection (docs/System_Architecture.md Open Decision #6). Batched per cycle
    rather than per sample to keep the topic at ~60 msg/s/bus instead of ~2k.
    """

    bus_id: str
    t0: float = Field(description="Epoch seconds of the first sample in the frame.")
    fs: float = Field(gt=0, description="Sample rate in Hz.")
    Va: list[float] = Field(default_factory=list)
    Vb: list[float] = Field(default_factory=list)
    Vc: list[float] = Field(default_factory=list)
    Ia: list[float] = Field(default_factory=list)
    Ib: list[float] = Field(default_factory=list)
    Ic: list[float] = Field(default_factory=list)


class FeederEvent(KafkaPayload):
    feeder: str
    timestamp: str
    features: dict[str, Any]


class AnomalyEvent(KafkaPayload):
    feeder: str
    verdict: dict[str, Any]
    topBuses: list[dict[str, Any]] = Field(default_factory=list)


class FaultTicketEvent(FaultTicket):
    incident_id: str


MESSAGE_MODELS = {
    "raw.signals": RawSignal,
    "feeder.events": FeederEvent,
    "anomalies.detected": AnomalyEvent,
    "faulttickets": FaultTicketEvent,
}


def validate_payload(topic: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a decoded Kafka payload for its topic."""
    model = MESSAGE_MODELS[topic]
    return model.model_validate(payload).model_dump(mode="python")
