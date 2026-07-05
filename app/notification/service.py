from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database import engine, fetch_all, fetch_one
from app.notification.constants import NotificationType
from app.notification.models import Notification
from app.notification.sse import sse_manager


async def create_notification(
    type: NotificationType,
    title: str,
    body: str,
    *,
    incident_id: str | None = None,
    bus_id: str | None = None,
    severity: str | None = None,
    push_sse: bool = True,
    sse_data: dict[str, Any] | None = None,
    conn: AsyncConnection | None = None,
) -> dict[str, Any]:
    """Persist an operator notification and broadcast it over SSE to all dashboards."""
    insert = (
        sa.insert(Notification)
        .values(
            type=type,
            title=title,
            body=body,
            incident_id=incident_id,
            bus_id=bus_id,
            severity=severity,
        )
        .returning(Notification)
    )
    row = await fetch_one(insert, connection=conn, commit_after=True)

    if push_sse:
        await sse_manager.push(
            event_type=type,
            data={
                "id": row["id"],  # type: ignore[index]
                "title": title,
                "body": body,
                "incident_id": incident_id,
                "bus_id": bus_id,
                "severity": severity,
                **(sse_data or {}),
            },
        )

    return row  # type: ignore[return-value]


async def list_notifications(conn: AsyncConnection | None = None) -> list[dict[str, Any]]:
    return await fetch_all(
        sa.select(Notification).order_by(Notification.created_at.desc()).limit(50),
        connection=conn,
    )


async def mark_all_read() -> None:
    async with engine.connect() as conn:
        await conn.execute(
            sa.update(Notification)
            .where(Notification.read.is_(False))
            .values(read=True)
        )
        await conn.commit()
