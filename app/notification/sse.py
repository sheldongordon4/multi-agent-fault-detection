import asyncio
import json
import logging
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


class BroadcastSSEManager:
    """
    In-process SSE broker for operator notifications.

    MAFD has no user accounts, so every connected dashboard subscribes to the same
    broadcast channel and receives every incident alert. Each open browser tab gets
    its own asyncio.Queue.
    """

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[dict]] = set()

    def _subscribe(self) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue()
        self._queues.add(q)
        logger.info("SSE subscribe (notifications) total=%d", len(self._queues))
        return q

    def _unsubscribe(self, q: asyncio.Queue[dict]) -> None:
        self._queues.discard(q)
        logger.info("SSE unsubscribe (notifications) total=%d", len(self._queues))

    async def push(self, event_type: str, data: dict) -> None:
        payload = {"type": event_type, **data}
        logger.info("SSE push type=%s subscribers=%d", event_type, len(self._queues))
        for q in list(self._queues):
            await q.put(payload)

    async def stream(self) -> AsyncGenerator[str, None]:
        """Yield raw SSE strings; heartbeat every 15 s of silence keeps proxies open."""
        q = self._subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(event)}\n\n"
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            self._unsubscribe(q)


sse_manager = BroadcastSSEManager()
