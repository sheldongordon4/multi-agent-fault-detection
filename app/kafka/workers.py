"""
Launches the MAFD consumer groups (docs/System_Architecture.md §3-§5).

Each entry is its own Kafka consumer group so the fan-out works:
    - raw.signals is consumed by streaming
  - faulttickets is consumed independently by notification AND persistence

`extraction` is the live bridge: it consumes raw.signals waveform frames and
publishes reduced rows to feeder.events, so detection is driven by real signals
rather than only by replayed rows (scripts/produce_events.py still replays for
offline work).

Run as background asyncio tasks from the FastAPI lifespan.
"""

import asyncio
import logging

from app.kafka import topics
from app.kafka.consumer import run_consumer, run_fast_consumer
from app.kafka.handlers import detect, diagnose, extract, notify, persist, stream

logger = logging.getLogger(__name__)

# group_id -> {topic: handler}
WORKERS: dict[str, dict] = {
    "extraction": {topics.RAW_SIGNALS: extract.handle},
    "detection": {topics.FEEDER_EVENTS: detect.handle},
    "streaming": {topics.RAW_SIGNALS: stream.handle},
    "coordinator": {topics.ANOMALIES_DETECTED: diagnose.handle},
    "notification": {topics.FAULT_TICKETS: notify.handle},
    "persistence": {topics.FAULT_TICKETS: persist.handle},
}

# Groups on the batched, auto-committing consumer instead of the default
# pause-and-commit-per-message one. Both raw.signals consumers qualify: their
# handlers are cheap and the topic is now a ~2k frames/s waveform firehose, where
# a synchronous commit per message was the documented ~1 msg/s cap.
#
# `extraction` accepts at-most-once for the same reason `streaming` does: a
# dropped frame costs a few samples out of a window, not a ticket. Everything
# downstream of feeder.events carries durable work and keeps explicit commits.
FAST_GROUPS: frozenset[str] = frozenset({"streaming", "extraction"})


def start_workers() -> list[asyncio.Task]:
    tasks = [
        asyncio.create_task(
            (run_fast_consumer if group_id in FAST_GROUPS else run_consumer)(
                group_id, handlers
            ),
            name=f"kafka-{group_id}",
        )
        for group_id, handlers in WORKERS.items()
    ]
    logger.info("Started %d Kafka consumer groups: %s", len(tasks), list(WORKERS))
    return tasks


async def stop_workers(tasks: list[asyncio.Task]) -> None:
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Stopped Kafka consumer groups")
