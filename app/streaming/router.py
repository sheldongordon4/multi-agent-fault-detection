from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.streaming.manager import signal_stream_manager

router = APIRouter(prefix="/stream", tags=["streaming"])


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
