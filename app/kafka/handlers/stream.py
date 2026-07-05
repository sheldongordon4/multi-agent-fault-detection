"""
Streaming service handler (docs/System_Architecture.md §4.4).

A separate consumer group on raw.signals: feeds each reading into the per-bus
rolling buffer / SSE fan-out so the UI live chart updates.
"""

import logging

from app.streaming.manager import signal_stream_manager

logger = logging.getLogger(__name__)


async def handle(reading: dict) -> None:
    bus_id = reading.get("bus_id", "unknown_bus")
    await signal_stream_manager.ingest(bus_id, reading)
