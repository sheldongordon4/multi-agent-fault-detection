import logging

from confluent_kafka.admin import AdminClient, NewTopic

from app.config import settings
from app.kafka import topics

logger = logging.getLogger(__name__)

ALL_TOPICS = [
    topics.RAW_SIGNALS,
    topics.FEEDER_EVENTS,
    topics.ANOMALIES_DETECTED,
    topics.FAULT_TICKETS,
]


def ensure_topics(num_partitions: int = 6, replication_factor: int = 1) -> None:
    """
    Create the MAFD topics (+ their `.dlq` companions) with a known partition
    count, so partition-by-key ordering is correct instead of relying on broker
    auto-create defaults. Idempotent: existing topics are left untouched.
    """
    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
    existing = set(admin.list_topics(timeout=10).topics.keys())

    wanted = ALL_TOPICS + [f"{t}.dlq" for t in ALL_TOPICS]
    to_create = [
        NewTopic(t, num_partitions=num_partitions, replication_factor=replication_factor)
        for t in wanted
        if t not in existing
    ]
    if not to_create:
        logger.info("Kafka topics already present.")
        return

    for topic, fut in admin.create_topics(to_create).items():
        try:
            fut.result()
            logger.info("Created topic %s", topic)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Topic %s not created: %s", topic, exc)
