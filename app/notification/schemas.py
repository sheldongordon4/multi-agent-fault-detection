from datetime import datetime

from pydantic import BaseModel

from app.notification.constants import NotificationType


class NotificationResponse(BaseModel):
    id: str
    type: NotificationType
    title: str
    body: str
    read: bool
    incident_id: str | None = None
    bus_id: str | None = None
    severity: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    unread_count: int
