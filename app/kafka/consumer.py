import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from confluent_kafka import Consumer, KafkaError, Message

from app.config import settings

logger = logging.getLogger(__name__)

Handler = Callable[[dict], Coroutine[Any, Any, None]]


async def _to_dlq(msg: Message, exc: BaseException) -> None:
    """Best-effort publish of a failed message to `<topic>.dlq` for inspection."""
    from app.kafka import producer

    try:
        raw = msg.value()
        key = msg.key()
        await producer.produce(
            f"{msg.topic()}.dlq",
            {
                "original_topic": msg.topic(),
                "error": repr(exc),
                "value": raw.decode(errors="replace") if raw else None,
            },
            key=key.decode(errors="replace") if key else None,
        )
    except Exception:
        logger.exception("failed to publish to DLQ for %s", msg.topic())


def _make_consumer(group_id: str) -> Consumer:
    return Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )


async def run_consumer(group_id: str, handlers: dict[str, Handler]) -> None:
    """
    Run one consumer group: subscribe to `handlers` keys and dispatch each message
    to its handler. Processes one message at a time.

    A handler can run for a long time (LLM calls, etc.). librdkafka evicts the
    consumer from the group if poll() is not called within max.poll.interval.ms,
    which would trigger endless rebalances. To avoid that, the handler runs as a
    background task while this loop keeps calling poll() — partitions are paused
    for the duration so those polls fetch nothing new and serve only as the
    keep-alive that librdkafka requires.

    Each call to run_consumer is its own consumer group, so two groups can both
    receive every message on a shared topic (notification + persistence fan-out).
    """
    consumer = await asyncio.to_thread(_make_consumer, group_id)
    topics = list(handlers.keys())
    consumer.subscribe(topics)
    logger.info("Kafka consumer group=%s subscribed to: %s", group_id, topics)

    processing: asyncio.Task[None] | None = None
    current: Message | None = None

    try:
        while True:
            try:
                msg = await asyncio.to_thread(consumer.poll, 1.0)

                # ── A handler is in flight ────────────────────────────
                if processing is not None and current is not None:
                    if not processing.done():
                        consumer.pause(consumer.assignment())
                        continue

                    exc = processing.exception()
                    if exc is None:
                        await asyncio.to_thread(consumer.commit, message=current)
                        logger.info("[%s] processed message from %s", group_id, current.topic())
                    else:
                        # Route the poison message to a dead-letter topic and commit
                        # anyway, so one bad message can't block offset progress for
                        # everything behind it. The DLQ preserves it for inspection.
                        logger.error(
                            "[%s] handler failed for topic %s; routing to DLQ",
                            group_id,
                            current.topic(),
                            exc_info=exc,
                        )
                        await _to_dlq(current, exc)
                        await asyncio.to_thread(consumer.commit, message=current)

                    consumer.resume(consumer.assignment())
                    processing = None
                    current = None
                    continue

                # Idle: find the next message to process
                if msg is None:
                    continue
                err = msg.error()
                if err:
                    if err.code() != KafkaError._PARTITION_EOF:
                        logger.error("[%s] kafka error: %s", group_id, err)
                    continue

                topic = msg.topic()
                if topic is None:
                    continue
                handler = handlers.get(topic)
                if handler is None:
                    continue

                raw_value = msg.value()
                if raw_value is None:
                    continue
                payload = json.loads(raw_value)
                logger.info("[%s] consuming message from %s", group_id, msg.topic())

                consumer.pause(consumer.assignment())
                current = msg
                processing = asyncio.create_task(handler(payload))

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[%s] consumer loop error; continuing", group_id)
                await asyncio.sleep(1)

    except asyncio.CancelledError:
        logger.info("[%s] kafka consumer shutting down", group_id)
        if processing is not None and not processing.done():
            processing.cancel()
    finally:
        await asyncio.to_thread(consumer.close)
