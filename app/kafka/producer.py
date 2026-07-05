import asyncio
import json
import logging

from confluent_kafka import Producer

from app.config import settings

logger = logging.getLogger(__name__)

_producer: Producer | None = None


def _get_producer() -> Producer:
    global _producer
    if _producer is None:
        _producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": "mafd-producer",
            }
        )
    return _producer


def _delivery_report(err, msg) -> None:
    if err:
        logger.error("Delivery failed for topic %s: %s", msg.topic(), err)
    else:
        logger.debug("Delivered to %s [%d] @ %d", msg.topic(), msg.partition(), msg.offset())


async def produce(topic: str, payload: dict, key: str | None = None) -> None:
    """
    Publish a JSON message. `key` sets the partition key (use bus_id / incident_id
    so all messages for one bus land on the same partition and stay ordered).
    """
    producer = _get_producer()
    value = json.dumps(payload).encode()
    key_bytes = key.encode() if key is not None else None
    await asyncio.to_thread(
        producer.produce, topic, value=value, key=key_bytes, callback=_delivery_report
    )
    await asyncio.to_thread(producer.flush)
