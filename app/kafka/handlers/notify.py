"""
Notification service handler (docs/System_Architecture.md §4.5).

Consumer group A on faulttickets: creates an operator notification and broadcasts
it over SSE to every connected dashboard.
"""

import logging

from app.notification import service as notif_service
from app.notification.constants import NotificationType

logger = logging.getLogger(__name__)


async def handle(ticket: dict) -> None:
    incident_id = ticket.get("incident_id")
    bus_id = ticket.get("bus_id")
    severity = ticket.get("severity")
    fault_type = ticket.get("fault_type", "Fault")

    await notif_service.create_notification(
        type=NotificationType.FAULT_TICKET_READY,
        title=f"{fault_type} on {bus_id}",
        body=f"A {severity or 'new'}-severity fault ticket was raised for {bus_id}.",
        incident_id=incident_id,
        bus_id=bus_id,
        severity=severity,
        sse_data={"ticket_id": ticket.get("ticket_id")},
    )
    logger.info("Notified dashboards for incident %s", incident_id)
