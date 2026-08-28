"""Pydantic contracts for messages crossing Kafka service boundaries."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.faults.schemas import FaultTicket


class KafkaPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class RawSignal(KafkaPayload):
    bus_id: str


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
