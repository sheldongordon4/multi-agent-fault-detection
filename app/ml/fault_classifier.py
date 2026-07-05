"""
fault_classifier.py — SUPERVISED short-circuit classifier + locator (Family 1,
docs/System_Architecture.md §6.1).

Complements the unsupervised fault_detector (fault vs normal) with WHAT the fault
is: fault_type, fault_category, and location (km). Trained on the labeled testbed
feature rows (RandomForest — strong on tabular, no extra deps). Persisted with its
feature-column list so an incoming event aligns to the exact columns/order the
model trained on.

Usage:
    from app.ml.fault_classifier import train_classifier, classify_event
    train_classifier()               # trains on the clean 13-bus testbed export
    classify_event(row)              # row: dict / Series / single-row DataFrame
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

ROOT_DIR = Path(__file__).resolve().parents[2]  # repo root (for scripts + data)
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from scripts.load_testbed import feature_columns  # noqa: E402

MODEL_DIR = Path(__file__).resolve().parent / "models"  # app/ml/models
MODEL_DIR.mkdir(parents=True, exist_ok=True)
CLASSIFIER_PATH = MODEL_DIR / "testbed_classifier.pkl"

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
    out = {"fault_type": str(bundle["type_clf"].predict(x)[0])}
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
