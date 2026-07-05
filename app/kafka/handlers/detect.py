"""
Detection service handler — EVENT path (docs/System_Architecture.md §4.2, §6.1).

Consumes feeder.events (pre-reduced per-bus event rows = the output of feature
extraction) and scores each with the testbed IsolationForest (app.ml.fault_detector).
On a fault it publishes anomalies.detected carrying the verdict + most-disturbed
buses. Detection is the TRIGGER — the coordinator runs no detection of its own
(detection-as-trigger), so everything it needs to diagnose travels in the event.
"""

import asyncio
import logging

from app.kafka import producer, topics
from app.ml.fault_classifier import classify_event, load_classifier
from app.ml.fault_detector import (
    load_testbed_model,
    publish_event,
    train_isoforest_on_testbed,
)

logger = logging.getLogger(__name__)

# NORMAL-only training set for the 13-bus feeder (unsupervised; labels ignored).
NORMAL_TRAIN_CSV = "data/generated/normal_train_013.csv"

_model = None
_feature_cols = None
_classifier: dict | None = None
_classifier_tried = False


def _get_model():
    global _model, _feature_cols
    if _model is None:
        try:
            _model, _feature_cols = load_testbed_model()
        except FileNotFoundError:
            logger.info("Testbed model missing; training on %s ...", NORMAL_TRAIN_CSV)
            train_isoforest_on_testbed(NORMAL_TRAIN_CSV)
            _model, _feature_cols = load_testbed_model()
    return _model, _feature_cols


def _get_classifier() -> dict | None:
    """Supervised classifier is OPTIONAL enrichment — return None if unavailable."""
    global _classifier, _classifier_tried
    if not _classifier_tried:
        _classifier_tried = True
        try:
            _classifier = load_classifier()
        except FileNotFoundError:
            logger.warning("Fault classifier not trained; publishing without classification.")
    return _classifier


async def handle(event: dict) -> None:
    # The event carries the per-bus feature row (under "features"); plain rows are
    # accepted too. publish_event ignores any non-feature columns.
    features = event.get("features", event)
    model, feature_cols = _get_model()

    payload = await asyncio.to_thread(
        publish_event,
        features,
        feeder=event.get("feeder"),
        timestamp=event.get("timestamp"),
        event_id=event.get("event_id"),
        model=model,
        feature_cols=feature_cols,
    )

    if not payload["verdict"]["isFault"]:
        return  # normal feeder snapshot — nothing to escalate

    incident_id = payload.get("eventId") or f"{payload.get('feeder')}:{payload.get('timestamp')}"
    payload["incident_id"] = incident_id

    # Supervised classification (Family 1): attach fault_type/category/location if
    # the classifier is available. Optional — never blocks the anomaly event.
    clf = _get_classifier()
    if clf is not None:
        try:
            payload["classification"] = await asyncio.to_thread(classify_event, features, clf)
        except Exception:
            logger.exception("Classification failed; publishing anomaly without it")

    # Ground truth (if the replay carried it) is for offline eval only — kept out
    # of the coordinator prompt to avoid label leakage.
    if "ground_truth" in event:
        payload["groundTruth"] = event["ground_truth"]

    await producer.produce(topics.ANOMALIES_DETECTED, payload, key=str(payload.get("feeder")))
    logger.info("Fault event on feeder %s -> incident %s", payload.get("feeder"), incident_id)
