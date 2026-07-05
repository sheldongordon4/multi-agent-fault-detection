"""
Persistence service handler (docs/System_Architecture.md §4.6).

Consumer group B on faulttickets: writes the ticket to Postgres (idempotent upsert
keyed by incident_id) for the ticket-history API.
"""

import logging

from app.persistence import service as persist_service

logger = logging.getLogger(__name__)


async def handle(ticket: dict) -> None:
    incident_id = ticket.get("incident_id") or ticket.get("ticket_id", "unknown")
    await persist_service.upsert_ticket(incident_id, ticket)
    logger.info("Persisted faultticket for incident %s", incident_id)
