"""
Detection service handler — EVENT path (docs/System_Architecture.md §4.2, §6.1).

Consumes feeder.events (pre-reduced per-bus event rows = the output of feature
extraction) and scores each with the testbed IsolationForest (app.ml.fault_detector).
On a fault it publishes anomalies.detected carrying the verdict + most-disturbed
buses. Detection is the TRIGGER — the coordinator runs no detection of its own
(detection-as-trigger), so everything it needs to diagnose travels in the event.
"""

import logging

from app.kafka import producer, topics
from app.kafka.executors import run_ml
from app.ml.scoring import classify_event_task, score_event_task

logger = logging.getLogger(__name__)


async def handle(event: dict) -> None:
    # The event carries the per-bus feature row (under "features"); plain rows are
    # accepted too. publish_event ignores any non-feature columns.
    features = event.get("features", event)

    # Runs in a separate PROCESS: sklearn scoring is CPU-bound Python, so on a
    # thread it holds the GIL and stalls the event loop — which is what froze the
    # live signal SSE whenever events came through. The model itself is loaded and
    # cached inside the worker, so only plain dicts cross the boundary.
    payload = await run_ml(
        score_event_task,
        features,
        feeder=event.get("feeder"),
        timestamp=event.get("timestamp"),
        event_id=event.get("event_id"),
    )

    if not payload["verdict"]["isFault"]:
        return  # normal feeder snapshot — nothing to escalate

    incident_id = payload.get("eventId") or f"{payload.get('feeder')}:{payload.get('timestamp')}"
    payload["incident_id"] = incident_id

    # Supervised classification (Family 1): attach fault_type/category/location if
    # the classifier is available. Optional — never blocks the anomaly event.
    try:
        classification = await run_ml(classify_event_task, features)
        if classification is not None:
            payload["classification"] = classification
    except Exception:
        logger.exception("Classification failed; publishing anomaly without it")

    # Ground truth (if the replay carried it) is for offline eval only — kept out
    # of the coordinator prompt to avoid label leakage.
    if "ground_truth" in event:
        payload["groundTruth"] = event["ground_truth"]

    await producer.produce(topics.ANOMALIES_DETECTED, payload, key=str(payload.get("feeder")))
    logger.info("Fault event on feeder %s -> incident %s", payload.get("feeder"), incident_id)
