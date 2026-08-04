from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.streaming.manager import signal_stream_manager
from app.streaming.schemas import BusListResponse

router = APIRouter(prefix="/stream", tags=["streaming"])


@router.get(
    "/buses",
    response_model=BusListResponse,
    summary="List buses with a live signal buffer",
)
async def list_buses() -> dict[str, Any]:
    """
    Buses the streaming service currently holds readings for. A bus only appears
    once it has received at least one reading off `raw.signals`, so this is empty
    until a signal producer runs. Drives the UI's bus selector.
    """
    items = signal_stream_manager.buses()
    return {"items": items, "count": len(items)}


@router.get("/signals")
async def stream_signals(
    bus_id: Annotated[str, Query(description="Bus to stream, e.g. bus_1")],
) -> StreamingResponse:
    """
    SSE live signal feed for one bus. On connect the client receives a snapshot of
    the bus's rolling buffer (~last 5 min), then live readings as they arrive.
    """
    return StreamingResponse(
        signal_stream_manager.stream(bus_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
