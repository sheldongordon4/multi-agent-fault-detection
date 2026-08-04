from enum import StrEnum


class NotificationType(StrEnum):
    INCIDENT_DETECTED = "incident.detected"
    FAULT_TICKET_READY = "faultticket.ready"
