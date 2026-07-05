from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database import get_db_connection
from app.notification import service as notif_service
from app.notification.schemas import NotificationListResponse
from app.notification.sse import sse_manager

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/stream")
async def notification_stream() -> StreamingResponse:
    """
    SSE endpoint for operator incident alerts. Connect once; the server broadcasts
    every new-incident / ticket-ready event to all connected dashboards.
    """
    return StreamingResponse(
        sse_manager.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
) -> dict[str, Any]:
    items = await notif_service.list_notifications(conn)
    unread_count = sum(1 for n in items if not n["read"])
    return {"items": items, "unread_count": unread_count}


@router.post("/read-all", status_code=204)
async def mark_all_read() -> None:
    await notif_service.mark_all_read()
