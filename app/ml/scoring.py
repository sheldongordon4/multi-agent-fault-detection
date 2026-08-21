"""
Process-pool entrypoints for the CPU-bound model work.

These exist so detection can run in a separate process (app/kafka/executors.py).
That imposes two constraints the handler code can't meet directly:

  * every argument and return value must be **picklable** — so these take plain
    dicts, never a live sklearn estimator;
  * the callables must be **importable at module level** — no closures, no bound
    methods.

Models are cached in process-local globals, so each worker loads them once on its
first call rather than having them pickled across the boundary per event.
"""

import logging
from typing import Any

from app.ml.fault_classifier import classify_event, load_classifier
from app.ml.fault_detector import (
    load_testbed_model,
    publish_event,
    train_isoforest_on_testbed,
)

logger = logging.getLogger(__name__)

# NORMAL-only training set for the 13-bus feeder (unsupervised; labels ignored).
NORMAL_TRAIN_CSV = "data/generated/normal_train_013.csv"

# Process-local caches — one set per worker process.
_model = None
_feature_cols = None
_classifier: dict | None = None
_classifier_tried = False


def get_model():
    """Load (or first train) the detection model, cached per process."""
    global _model, _feature_cols
    if _model is None:
        try:
            _model, _feature_cols = load_testbed_model()
        except FileNotFoundError:
            logger.info("Testbed model missing; training on %s ...", NORMAL_TRAIN_CSV)
            train_isoforest_on_testbed(NORMAL_TRAIN_CSV)
            _model, _feature_cols = load_testbed_model()
    return _model, _feature_cols


def get_classifier() -> dict | None:
    """Supervised classifier is OPTIONAL enrichment — return None if unavailable."""
    global _classifier, _classifier_tried
    if not _classifier_tried:
        _classifier_tried = True
        try:
            _classifier = load_classifier()
        except FileNotFoundError:
            logger.warning("Fault classifier not trained; publishing without classification.")
    return _classifier


def score_event_task(
    features: dict,
    feeder: Any = None,
    timestamp: Any = None,
    event_id: Any = None,
) -> dict:
    """Score one per-bus feature row. Returns the anomalies.detected payload."""
    model, feature_cols = get_model()
    return publish_event(
        features,
        feeder=feeder,
        timestamp=timestamp,
        event_id=event_id,
        model=model,
        feature_cols=feature_cols,
    )


def classify_event_task(features: dict) -> dict | None:
    """Attach fault type/category/location. Returns None when untrained."""
    clf = get_classifier()
    if clf is None:
        return None
    return classify_event(features, clf)


def warm_models() -> None:
    """
    Load (and if necessary train) the models once, in the parent, at startup.

    Without this the first event could have several worker processes discover a
    missing model file simultaneously and all start training it — racing to write
    the same artefact. Warming first means workers only ever load.
    """
    get_model()
    get_classifier()
