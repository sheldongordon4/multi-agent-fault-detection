"""
fault_classifier.py — SUPERVISED short-circuit classifier + locator (Family 1,
docs/System_Architecture.md §6.1).

Complements the unsupervised fault_detector (fault vs normal) with WHAT the fault
is: fault_type, fault_category, and location (km). Trained on the labeled testbed
feature rows (RandomForest — strong on tabular, no extra deps). Persisted with its
feature-column list so an incoming event aligns to the exact columns/order the
model trained on.

Usage:
    from ml.fault_classifier import train_classifier, classify_event
    train_classifier()               # trains on the clean 13-bus testbed export
    classify_event(row)              # row: dict / Series / single-row DataFrame
"""

from __future__ import annotations

import logging
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

# Repo root by marker file, not by counting parents: this module has moved
# between app/ml/ and ml/, and a hard-coded depth breaks silently when it does
# (paths resolve outside the repo and data simply looks absent).
ROOT_DIR = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from scripts.load_testbed import feature_columns  # noqa: E402

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent / "models"  # ml/models
MODEL_DIR.mkdir(parents=True, exist_ok=True)
CLASSIFIER_PATH = MODEL_DIR / "fault_classifier.pkl"

# The CLEAN 13-bus export (labeled; see scripts/analyze_testbed.py).
DEFAULT_TRAIN_CSV = "data/testbed/013 Bus Fault Analysis Batch (mod).csv"


def _resolve(csv_path) -> Path:
    p = Path(csv_path)
    return p if p.is_absolute() else ROOT_DIR / p


def train_classifier(
    csv_path=DEFAULT_TRAIN_CSV, n_estimators: int = 200, random_state: int = 42
) -> Path:
    """Train fault_type + fault_category classifiers and a location regressor."""
    df = pd.read_csv(_resolve(csv_path))
    feats = feature_columns(df)
    X = df[feats].apply(pd.to_numeric, errors="coerce")

    finite = np.isfinite(X.to_numpy()).all(axis=1)
    X = X[finite].reset_index(drop=True)
    df = df[finite].reset_index(drop=True)

    type_clf = RandomForestClassifier(n_estimators=n_estimators, random_state=random_state)
    type_clf.fit(X.values, df["target_fault_type"].astype(str))

    cat_clf = None
    if "target_fault_category" in df.columns:
        cat_clf = RandomForestClassifier(n_estimators=n_estimators, random_state=random_state)
        cat_clf.fit(X.values, df["target_fault_category"].astype(str))

    loc_reg = None
    if "target_location_km" in df.columns:
        y_loc = pd.to_numeric(df["target_location_km"], errors="coerce").fillna(0.0)
        loc_reg = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state)
        loc_reg.fit(X.values, y_loc.values)

    with open(CLASSIFIER_PATH, "wb") as f:
        pickle.dump(
            {"type_clf": type_clf, "cat_clf": cat_clf, "loc_reg": loc_reg, "feature_cols": feats},
            f,
        )
    print(f"Trained classifier on {len(X)} rows ({len(feats)} features) -> {CLASSIFIER_PATH}")
    return CLASSIFIER_PATH


def load_classifier() -> dict:
    if not CLASSIFIER_PATH.exists():
        raise FileNotFoundError(
            f"Classifier not found at {CLASSIFIER_PATH}. Train it via train_classifier()."
        )
    with open(CLASSIFIER_PATH, "rb") as f:
        return pickle.load(f)


# How many runner-up classes to report beside the prediction. Two is enough to
# show what the model was torn between without turning the ticket into a
# probability table.
_N_ALTERNATIVES = 2


def _type_confidence(clf, x) -> dict:
    """
    How sure the classifier is, and what it nearly said instead.

    The ticket asserted a fault type flatly, which reads as certainty the model
    does not have. A RandomForest already computes class probabilities on the
    way to its prediction, so the number was being discarded rather than
    missing.

    It matters most exactly where this system is weakest. SLG and LLG are both
    ground faults and sit close together in feature space; an operator who can
    see "SLG 61%, LLG 34%" knows to check the sequence ratios themselves, while
    a bare "SLG" invites them not to. Publishing the runner-up is the honest
    form of that: the alternative IS the diagnosis when the margin is thin.

    Returns {} when the estimator has no predict_proba, so a swapped model class
    degrades to the old behaviour instead of failing.
    """
    proba = getattr(clf, "predict_proba", None)
    classes = getattr(clf, "classes_", None)
    if proba is None or classes is None:
        return {}

    try:
        scores = proba(x)[0]
    except Exception:  # pragma: no cover - estimator without a fitted proba
        logger.warning("Classifier has predict_proba but it failed; omitting confidence.")
        return {}

    ranked = sorted(zip(classes, scores, strict=False), key=lambda p: float(p[1]), reverse=True)
    return {
        "confidence": round(float(ranked[0][1]), 4),
        "alternatives": [
            {"fault_type": str(name), "confidence": round(float(score), 4)}
            for name, score in ranked[1 : 1 + _N_ALTERNATIVES]
            if float(score) > 0.0
        ],
    }


def classify_event(features, bundle: dict | None = None) -> dict:
    """Predict fault_type / fault_category / location_km for one event's features."""
    if bundle is None:
        bundle = load_classifier()
    fcols = bundle["feature_cols"]

    if isinstance(features, pd.DataFrame):
        row = features.iloc[0]
    elif isinstance(features, pd.Series):
        row = features
    else:
        row = pd.Series(features)

    missing = [c for c in fcols if c not in row.index]
    if missing:
        raise ValueError(
            f"event missing {len(missing)} of {len(fcols)} classifier features "
            f"(e.g. {missing[:3]}). Wrong feeder?"
        )

    x = pd.to_numeric(row[fcols], errors="coerce").to_numpy(dtype=float).reshape(1, -1)
    # Guard inf/nan (de-energized buses, docs §11) so sklearn scores instead of
    # raising — matches fault_detector.detect_event.
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    out: dict = {"fault_type": str(bundle["type_clf"].predict(x)[0])}
    out.update(_type_confidence(bundle["type_clf"], x))
    if bundle.get("cat_clf") is not None:
        out["fault_category"] = str(bundle["cat_clf"].predict(x)[0])
    if bundle.get("loc_reg") is not None:
        out["location_km"] = round(float(bundle["loc_reg"].predict(x)[0]), 3)
    return out


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Train the supervised fault classifier + locator.")
    p.add_argument("--csv", default=DEFAULT_TRAIN_CSV)
    args = p.parse_args()
    train_classifier(args.csv)
