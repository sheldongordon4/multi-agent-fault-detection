"""
fault_detector.py — IsolationForest fault TRIGGER on the testbed event schema.

This is the project's primary detector. One row = one fault EVENT across all of a
feeder's monitored buses, already reduced to per-bus features (30 cols on the
13-bus feeder, 42 on the 34-bus). There is no time axis and no anomaly windows.

(The legacy time-series detector in app/ml/baseline_detector.py is deprecated and
is not part of the live pipeline.)

The model is trained on synthetic NORMAL rows (scripts/generate_normal_data.py)
and persisted together with its feature-column list, so detect_event() aligns an
incoming event to the exact columns/order the model trained on (feeder-specific:
a 13-bus model cannot silently mis-score a 34-bus event).

Usage:
    from app.ml.fault_detector import train_isoforest_on_testbed, detect_event
    train_isoforest_on_testbed("data/generated/normal_train_013.csv")
    detect_event(row)        # row: dict / pandas Series / single-row DataFrame

    # or from the CLI:
    .venv/Scripts/python.exe app/ml/fault_detector.py --csv data/generated/normal_train_013.csv
"""

from __future__ import annotations

import pickle
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

ROOT_DIR = Path(__file__).resolve().parents[2]  # repo root (for scripts + data)
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from scripts.load_testbed import load_testbed  # noqa: E402

MODEL_DIR = Path(__file__).resolve().parent / "models"  # app/ml/models
MODEL_DIR.mkdir(parents=True, exist_ok=True)
# Kept separate from baseline_isolation_forest.pkl (the legacy time-series model)
# so neither path clobbers the other.
TESTBED_MODEL_PATH = MODEL_DIR / "testbed_isolation_forest.pkl"

# Per-bus feature families (used to read a row back per bus for the publish payload).
FEATURE_FAMILIES = [
    "min_Va_fault_pu",
    "max_Ia_fault",
    "max_I0_I1_fault",
    "max_I2_I1_fault",
    "mean_Vunb_fault",
    "recovery_Va_post",
]


def train_isoforest_on_testbed(
    csv_path,
    contamination: float = 0.01,
    n_estimators: int = 200,
    random_state: int = 42,
) -> IsolationForest:
    """
    Train the IsolationForest fault trigger on a NORMAL-only testbed CSV.

    The CSV is in the per-bus feature schema (e.g. data/generated/
    normal_train_013.csv). Labels are ignored — the model is unsupervised. The
    trained model is persisted TOGETHER with its feature-column list, so
    detect_event() can align an incoming event to the exact columns/order the
    model trained on.

    contamination defaults to 0.01 (tuned on the 13-bus feeder; see
    scripts/validate_isoforest.py).
    """
    X, _, feature_cols = load_testbed(csv_path, target_col="target_fault_type")

    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
    )
    model.fit(X.values)

    with open(TESTBED_MODEL_PATH, "wb") as f:
        pickle.dump(
            {
                "model": model,
                "feature_cols": feature_cols,
                "contamination": contamination,
            },
            f,
        )
    print(
        f"Trained testbed IsolationForest on {len(X)} normal rows "
        f"({len(feature_cols)} features) -> {TESTBED_MODEL_PATH}"
    )
    return model


def load_testbed_model():
    """Load the persisted testbed model + its feature columns (model, feature_cols)."""
    if not TESTBED_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Testbed model not found at {TESTBED_MODEL_PATH}. "
            f"Train it first via train_isoforest_on_testbed(<normal_csv>)."
        )
    with open(TESTBED_MODEL_PATH, "rb") as f:
        bundle = pickle.load(f)
    return bundle["model"], bundle["feature_cols"]


def detect_event(features, model=None, feature_cols=None) -> dict:
    """
    Score ONE testbed-format event (one feeder snapshot) as normal vs fault.

    Args:
        features: the event's per-bus features as a dict {column: value}, a
                  pandas Series, or a single-row DataFrame. Must contain at
                  least the model's feature columns (extras are ignored).
        model, feature_cols: optionally pass a preloaded model + columns (e.g.
                  when scoring many events in a loop); otherwise the persisted
                  testbed model is loaded.

    Returns:
        dict with isFault (bool), anomalyScore (higher = more anomalous),
        decisionFunction (raw sklearn score; higher = more normal) and nFeatures.
    """
    if model is None or feature_cols is None:
        model, feature_cols = load_testbed_model()

    if isinstance(features, pd.DataFrame):
        row = features.iloc[0]
    elif isinstance(features, pd.Series):
        row = features
    else:
        row = pd.Series(features)

    missing = [c for c in feature_cols if c not in row.index]
    if missing:
        raise ValueError(
            f"event is missing {len(missing)} of {len(feature_cols)} feature "
            f"columns (e.g. {missing[:3]}). Wrong feeder?"
        )

    x = pd.to_numeric(row[feature_cols], errors="coerce").to_numpy(dtype=float).reshape(1, -1)
    # De-energized/islanded buses arrive as inf/nan (docs/System_Architecture.md §11);
    # sklearn rejects non-finite input, so guard to 0.0 (mirrors the feature
    # extractor's _reduce_bus) instead of letting the severe faults error out.
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    raw = float(model.decision_function(x)[0])  # higher = more normal
    pred = int(model.predict(x)[0])  # -1 = anomaly, 1 = normal
    return {
        "isFault": pred == -1,
        "anomalyScore": -raw,  # higher = more anomalous
        "decisionFunction": raw,
        "nFeatures": len(feature_cols),
    }


def _detect_buses(feature_cols):
    """Recover the bus ids (in column order) from a feature-column list."""
    buses = []
    for c in feature_cols:
        for fam in FEATURE_FAMILIES:
            pref = fam + "_"
            if c.startswith(pref):
                bus = c[len(pref) :]
                if bus not in buses:
                    buses.append(bus)
    return buses


def _severity(is_fault: bool, anomaly_score: float) -> str:
    """Bucket the anomaly score (same thresholds as the legacy payload)."""
    if not is_fault:
        return "none"
    s = abs(anomaly_score)
    if s < 0.05:
        return "low"
    if s < 0.15:
        return "moderate"
    return "high"


def publish_event(
    features,
    *,
    feeder=None,
    timestamp=None,
    window_start=None,
    window_end=None,
    event_id=None,
    model=None,
    feature_cols=None,
    top_k: int = 3,
) -> dict:
    """
    Score one event and wrap it in a publish-ready payload.

    Layers three things on top of the bare detect_event() verdict:
      - context the extraction layer knows (feeder, window timestamps) — passed
        in, never invented here;
      - a severity bucket derived from the anomaly score;
      - the most-disturbed buses (ranked by deepest voltage sag) so the event is
        actionable, not just a yes/no.

    Returns a JSON-serializable dict.
    """
    if model is None or feature_cols is None:
        model, feature_cols = load_testbed_model()

    verdict = detect_event(features, model, feature_cols)

    # Normalize the row so we can read individual bus values back out.
    if isinstance(features, pd.DataFrame):
        row = features.iloc[0]
    elif isinstance(features, pd.Series):
        row = features
    else:
        row = pd.Series(features)
    row = pd.to_numeric(row, errors="coerce")

    bus_rows = []
    for bus in _detect_buses(feature_cols):
        vals = {}
        for fam in ("min_Va_fault_pu", "max_Ia_fault", "max_I0_I1_fault", "max_I2_I1_fault"):
            col = f"{fam}_{bus}"
            v = row[col] if col in row.index else None
            vals[fam] = float(v) if v is not None and pd.notna(v) else None
        min_va = vals["min_Va_fault_pu"]
        bus_rows.append(
            {
                "bus": bus,
                "minVa": round(min_va, 4) if min_va is not None else None,
                "maxIa": round(vals["max_Ia_fault"], 2)
                if vals["max_Ia_fault"] is not None
                else None,
                "maxI0I1": round(vals["max_I0_I1_fault"], 4)
                if vals["max_I0_I1_fault"] is not None
                else None,
                "maxI2I1": round(vals["max_I2_I1_fault"], 4)
                if vals["max_I2_I1_fault"] is not None
                else None,
                "_sag": (1.0 - min_va) if min_va is not None else -1.0,
            }
        )
    # Rank by deepest voltage sag (most disturbed first), then drop the sort key.
    bus_rows.sort(key=lambda d: d["_sag"], reverse=True)
    top_buses = [{k: v for k, v in d.items() if k != "_sag"} for d in bus_rows[:top_k]]

    ts = timestamp or datetime.now(UTC).isoformat()
    eid = event_id or f"evt_{ts}_{feeder or 'feeder'}"

    return {
        "eventId": eid,
        "feeder": feeder,
        "timestamp": ts,
        "windowStart": window_start,
        "windowEnd": window_end,
        "verdict": {
            "isFault": verdict["isFault"],
            "anomalyScore": round(verdict["anomalyScore"], 4),
            "severity": _severity(verdict["isFault"], verdict["anomalyScore"]),
        },
        "topBuses": top_buses,
        "model": {
            "type": "IsolationForest",
            "nFeatures": verdict["nFeatures"],
            "contamination": getattr(model, "contamination", None),
        },
    }


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(
        description="Train the testbed event-model IsolationForest on a normal CSV."
    )
    p.add_argument(
        "--csv",
        default="data/generated/normal_train_013.csv",
        help="NORMAL-only testbed CSV to train on.",
    )
    p.add_argument("--contamination", type=float, default=0.01)
    args = p.parse_args()
    train_isoforest_on_testbed(args.csv, contamination=args.contamination)
