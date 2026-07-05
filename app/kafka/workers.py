"""
Launches the MAFD consumer groups (docs/System_Architecture.md §3-§5).

Each entry is its own Kafka consumer group so the fan-out works:
  - raw.signals is consumed independently by detection AND streaming
  - faulttickets is consumed independently by notification AND persistence

Run as background asyncio tasks from the FastAPI lifespan.
"""

import asyncio
import logging

from app.kafka import topics
from app.kafka.consumer import run_consumer
from app.kafka.handlers import detect, diagnose, notify, persist, stream

logger = logging.getLogger(__name__)

# group_id -> {topic: handler}
WORKERS: dict[str, dict] = {
    "detection": {topics.FEEDER_EVENTS: detect.handle},
    "streaming": {topics.RAW_SIGNALS: stream.handle},
    "coordinator": {topics.ANOMALIES_DETECTED: diagnose.handle},
    "notification": {topics.FAULT_TICKETS: notify.handle},
    "persistence": {topics.FAULT_TICKETS: persist.handle},
}


def start_workers() -> list[asyncio.Task]:
    tasks = [
        asyncio.create_task(run_consumer(group_id, handlers), name=f"kafka-{group_id}")
        for group_id, handlers in WORKERS.items()
    ]
    logger.info("Started %d Kafka consumer groups: %s", len(tasks), list(WORKERS))
    return tasks


async def stop_workers(tasks: list[asyncio.Task]) -> None:
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Stopped Kafka consumer groups")
