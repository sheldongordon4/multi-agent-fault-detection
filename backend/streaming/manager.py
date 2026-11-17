import asyncio
import json
import logging
from collections import defaultdict, deque
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

# ~5 minutes of per-second readings per bus (docs/System_Architecture.md §8).
BUFFER_MAXLEN = 300


class SignalStreamManager:
    """
    The Streaming service (§4.4, §8): maintains an in-memory rolling buffer per bus
    and fans out live readings to UI clients over SSE.

    A single buffer per bus is kept here (not per browser). On connect, a client
    gets a snapshot of its selected bus's buffer, then live updates for that bus
    only. Old data rolls off the bounded deque automatically.
    """

    def __init__(self, maxlen: int = BUFFER_MAXLEN) -> None:
        self._maxlen = maxlen
        self._buffers: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=maxlen))
        self._subscribers: dict[str, set[asyncio.Queue[dict]]] = defaultdict(set)

    async def ingest(self, bus_id: str, reading: dict) -> None:
        """Append a reading to its bus buffer and push it to that bus's subscribers."""
        self._buffers[bus_id].append(reading)
        for q in list(self._subscribers.get(bus_id, [])):
            await q.put(reading)

    def _subscribe(self, bus_id: str) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue()
        self._subscribers[bus_id].add(q)
        logger.info("signal stream subscribe bus=%s total=%d", bus_id, len(self._subscribers[bus_id]))
        return q

    def _unsubscribe(self, bus_id: str, q: asyncio.Queue[dict]) -> None:
        self._subscribers[bus_id].discard(q)
        if not self._subscribers[bus_id]:
            del self._subscribers[bus_id]
        logger.info("signal stream unsubscribe bus=%s", bus_id)

    def snapshot(self, bus_id: str) -> list[dict]:
        return list(self._buffers.get(bus_id, ()))

    def buses(self) -> list[str]:
        """Buses that have received at least one reading (i.e. have a live buffer)."""
        return sorted(self._buffers.keys())

    async def stream(self, bus_id: str) -> AsyncGenerator[str, None]:
        """Yield a snapshot of the bus buffer, then live readings; heartbeat on silence."""
        q = self._subscribe(bus_id)
        try:
            snapshot = {"type": "snapshot", "bus_id": bus_id, "readings": self.snapshot(bus_id)}
            yield f"data: {json.dumps(snapshot)}\n\n"
            while True:
                try:
                    reading = await asyncio.wait_for(q.get(), timeout=15)
                    event = {"type": "reading", "bus_id": bus_id, **reading}
                    yield f"data: {json.dumps(event)}\n\n"
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            self._unsubscribe(bus_id, q)


signal_stream_manager = SignalStreamManager()
