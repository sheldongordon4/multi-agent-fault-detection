import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from confluent_kafka import Consumer, KafkaError, Message

from app.config import settings
from app.kafka.executors import run_kafka
from app.kafka.schemas import validate_payload

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
    consumer = await run_kafka(_make_consumer, group_id)
    topics = list(handlers.keys())
    consumer.subscribe(topics)
    logger.info("Kafka consumer group=%s subscribed to: %s", group_id, topics)

    processing: asyncio.Task[None] | None = None
    current: Message | None = None

    # Poll timeout: long when idle (don't busy-spin waiting for new messages),
    # short while a handler is in flight so we notice its (usually millisecond-fast)
    # completion promptly instead of stalling a full second per message. The long
    # in-flight poll was the ~1 msg/s cap; partitions are paused during a handler,
    # so a short poll here still serves only as the librdkafka keep-alive.
    IDLE_POLL_S = 1.0
    BUSY_POLL_S = 0.05

    try:
        while True:
            try:
                poll_timeout = BUSY_POLL_S if processing is not None else IDLE_POLL_S
                msg = await run_kafka(consumer.poll, poll_timeout)

                # ── A handler is in flight
                if processing is not None and current is not None:
                    if not processing.done():
                        consumer.pause(consumer.assignment())
                        continue

                    exc = processing.exception()
                    if exc is None:
                        await run_kafka(consumer.commit, message=current)
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
                        await run_kafka(consumer.commit, message=current)

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
                try:
                    payload = json.loads(raw_value)
                except (ValueError, TypeError) as exc:
                    # Poison-on-decode: route to the DLQ and commit so it can't be
                    # silently skipped or endlessly redelivered (the handler-level
                    # DLQ below never sees it — decode happens before dispatch).
                    logger.error(
                        "[%s] undecodable message from %s; routing to DLQ",
                        group_id,
                        topic,
                        exc_info=exc,
                    )
                    await _to_dlq(msg, exc)
                    await run_kafka(consumer.commit, message=msg)
                    continue
                if not isinstance(payload, dict):
                    exc = ValueError("Kafka payload must be a JSON object")
                    await _to_dlq(msg, exc)
                    await asyncio.to_thread(consumer.commit, message=msg)
                    continue
                try:
                    payload = validate_payload(topic, payload)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "[%s] invalid message from %s; routing to DLQ",
                        group_id,
                        topic,
                        exc_info=exc,
                    )
                    await _to_dlq(msg, exc)
                    await asyncio.to_thread(consumer.commit, message=msg)
                    continue
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
        await run_kafka(consumer.close)


def _make_fast_consumer(group_id: str) -> Consumer:
    """
    Consumer tuned for a high-rate topic.

    Differences from `_make_consumer`: offsets auto-commit on a timer instead of
    one synchronous commit per message, and fetches are allowed to accumulate a
    little so a poll returns a batch rather than a single reading.
    """
    return Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": group_id,
            # `latest`: a UI live-chart feed wants what's happening now, not a
            # replay of everything buffered while nobody was watching.
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
            "auto.commit.interval.ms": 2000,
            "fetch.wait.max.ms": 50,
        }
    )


async def run_fast_consumer(
    group_id: str,
    handlers: dict[str, Handler],
    batch_size: int = 200,
    poll_timeout: float = 0.2,
) -> None:
    """
    Fast path for the `raw.signals` firehose (docs/System_Architecture.md §16).

    `run_consumer` is built for slow handlers: it pauses the partitions, runs the
    handler as a task, keeps polling as a keep-alive, then commits — several
    thread hops and a synchronous commit **per message**. That is right for the
    coordinator (one LLM call per incident) and hopeless for 20 readings/second,
    where it was the documented ~1 msg/s cap and left the live chart starved.

    Here the handler is trivial (append to a deque, push to subscriber queues), so
    the pause/commit ceremony buys nothing. We consume in batches and let offsets
    commit on a timer.

    Trade-off: at-most-once for this topic. A crash can drop a few readings from
    the live chart, which is acceptable — they're transient UI data with a bounded
    in-memory buffer, not tickets. Anything durable stays on `run_consumer`.
    """
    consumer = await run_kafka(_make_fast_consumer, group_id)
    topics_list = list(handlers.keys())
    consumer.subscribe(topics_list)
    logger.info(
        "Kafka FAST consumer group=%s subscribed to: %s (batch=%d)",
        group_id,
        topics_list,
        batch_size,
    )

    try:
        while True:
            try:
                messages = await run_kafka(consumer.consume, batch_size, poll_timeout)
                if not messages:
                    continue

                for msg in messages:
                    err = msg.error()
                    if err:
                        if err.code() != KafkaError._PARTITION_EOF:
                            logger.error("[%s] kafka error: %s", group_id, err)
                        continue

                    handler = handlers.get(msg.topic() or "")
                    if handler is None:
                        continue

                    raw_value = msg.value()
                    if raw_value is None:
                        continue

                    try:
                        payload = json.loads(raw_value)
                    except (ValueError, TypeError):
                        # No DLQ round-trip on the hot path — a malformed reading
                        # is not worth a produce() per message here.
                        logger.warning("[%s] undecodable message from %s", group_id, msg.topic())
                        continue

                    try:
                        await handler(payload)
                    except Exception:
                        logger.exception(
                            "[%s] handler failed for %s; dropping reading",
                            group_id,
                            msg.topic(),
                        )

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[%s] fast consumer loop error; continuing", group_id)
                await asyncio.sleep(1)

    except asyncio.CancelledError:
        logger.info("[%s] kafka fast consumer shutting down", group_id)
    finally:
        await run_kafka(consumer.close)
