"""
Coordinator service handler (docs/System_Architecture.md §4.3).

Consumes anomalies.detected and runs the LLM coordinator (kb_retrieve -> validated
FaultTicket) on the detection result (detection-as-trigger), stamps the incident_id,
and publishes faulttickets. The coordinator call is synchronous (LLM + RAG), so it
runs in a worker thread to keep the consumer's event loop responsive.
"""

import asyncio
import logging

from app.faults.service import run_fault_diagnosis
from app.kafka import producer, topics

logger = logging.getLogger(__name__)


async def handle(event: dict) -> None:
    incident_id = event.get("incident_id", "unknown")
    feeder = event.get("feeder")

    logger.info("Diagnosing incident %s (feeder=%s)", incident_id, feeder)

    ticket = await asyncio.to_thread(run_fault_diagnosis, event)
    ticket["incident_id"] = incident_id

    await producer.produce(topics.FAULT_TICKETS, ticket, key=incident_id)
    logger.info("Published faultticket for incident %s", incident_id)
