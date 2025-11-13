from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional, Dict

import datetime as dt
import numpy as np
import pandas as pd
import sqlite3
from sklearn.ensemble import IsolationForest

# Project root is one level up from ml/
ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "data" / "synthetic_signals.db"
MODEL_DIR = ROOT_DIR / "ml" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "baseline_isolation_forest.pkl"


FEATURE_COLUMNS = ["voltage_kv", "current_a", "frequency_hz"]
ScenarioName = Literal["normal", "overload_trip", "miscoordination", "theft_overload"]


@dataclass
class DetectionResult:
    scenario: str
    bus_id: str
    timestamps: List[str]
    anomaly_scores: List[float]
    anomaly_flags: List[int]
    summary_score: float
    n_points: int
    n_anomalies: int


def detection_result_to_payload(result: DetectionResult) -> dict:
    """
    Mixed payload version:
    - summary + macro anomalyWindows for agents / UI
    """

    # 1) Build detailed windows from pointwise flags
    detailed_windows = _compute_anomaly_windows(
        result.timestamps,
        result.anomaly_flags,
    )

    # 2) Compress into macro windows (what agents / UI will mostly use)
    macro_windows = _compress_windows(
        detailed_windows,
        max_gap_seconds=10,  # merge windows with small gaps
        min_points=5,        # drop one-off blips
    )

    # 3) Compute polished summary fields

    # We already flipped IsolationForest decision_function earlier so that
    # higher == more anomalous, but summary_score may still be negative.
    # For interpretability, we treat severity as a positive magnitude.
    mean_severity = abs(result.summary_score)

    # Fraction of points flagged as anomalous
    anomaly_rate = result.n_anomalies / result.n_points if result.n_points > 0 else 0.0

    # Simple severity buckets (you can tweak thresholds later)
    if mean_severity < 0.05:
        severity_level = "low"
    elif mean_severity < 0.15:
        severity_level = "moderate"
    else:
        severity_level = "high"

    # 4) Build the payload dict

    return {
        "scenario": result.scenario,
        "busId": result.bus_id,
        "summary": {
            "nPoints": result.n_points,
            "nAnomalies": result.n_anomalies,
            "anomalyRate": anomaly_rate,
            "meanSeverity": mean_severity,
            "severityLevel": severity_level,
        },
        "anomalyWindows": macro_windows,  # the short list you saw in your last run
        "meta": {
            "features": FEATURE_COLUMNS,
            "modelType": "IsolationForest",
            "modelPath": str(MODEL_PATH),
        },
    }


def _compute_anomaly_windows(
    timestamps: list[str],
    flags: list[int],
) -> list[dict]:
    """
    Compress pointwise anomaly flags into contiguous windows.

    Each window is a dict: {start, end, nPoints}
    """
    windows = []
    start_idx = None

    for i, flag in enumerate(flags):
        if flag == 1 and start_idx is None:
            start_idx = i  # start of a new window
        elif flag == 0 and start_idx is not None:
            # window ended at i-1
            windows.append(
                {
                    "start": str(timestamps[start_idx]),
                    "end": str(timestamps[i - 1]),
                    "nPoints": i - start_idx,
                }
            )
            start_idx = None

    # If we ended inside a window, close it
    if start_idx is not None:
        windows.append(
            {
                "start": str(timestamps[start_idx]),
                "end": str(timestamps[len(flags) - 1]),
                "nPoints": len(flags) - start_idx,
            }
        )

    return windows



def _compress_windows(
    windows: List[dict],
    max_gap_seconds: int = 10,
    min_points: int = 5,
) -> List[dict]:
    """
    Compress many small windows into coarser 'macro windows'.

    - Drops very short blips (nPoints < min_points).
    - Merges windows where the gap between them is <= max_gap_seconds.
    """

    # Filter out tiny windows first
    filtered = [w for w in windows if w["nPoints"] >= min_points]
    if not filtered:
        return []

    # Sort by start time just in case
    filtered.sort(key=lambda w: w["start"])

    def parse_ts(ts: str) -> dt.datetime:
        # Handles '2025-01-01 00:24:00' style timestamps
        return pd.to_datetime(ts).to_pydatetime()

    compressed: List[Dict] = []
    current = dict(filtered[0])  # copy

    for w in filtered[1:]:
        current_end = parse_ts(current["end"])
        next_start = parse_ts(w["start"])
        gap = (next_start - current_end).total_seconds()

        if gap <= max_gap_seconds:
            # Merge into current window
            current["end"] = max(current["end"], w["end"])
            current["nPoints"] += w["nPoints"]
        else:
            # Commit current and start a new one
            compressed.append(current)
            current = dict(w)

    # Commit the last one
    compressed.append(current)
    return compressed


def _connect_db():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"SQLite DB not found at {DB_PATH}. Run load_to_sqlite first.")
    return sqlite3.connect(DB_PATH)


def _load_signals(
    scenario: Optional[ScenarioName] = None,
    bus_id: Optional[str] = None,
) -> pd.DataFrame:
    conn = _connect_db()
    query = "SELECT * FROM signals WHERE 1=1"
    params = []

    if scenario is not None:
        query += " AND scenario = ?"
        params.append(scenario)

    if bus_id is not None:
        query += " AND bus_id = ?"
        params.append(bus_id)

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def train_baseline_detector(random_state: int = 42) -> IsolationForest:
    """
    Train an IsolationForest on normal scenario data across all buses.
    """
    df = _load_signals(scenario="normal")
    if df.empty:
        raise ValueError("No normal scenario data found in DB.")

    X = df[FEATURE_COLUMNS].values

    model = IsolationForest(
        n_estimators=200,
        contamination=0.02,  # small proportion expected as anomalies in normal
        random_state=random_state,
    )

    model.fit(X)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    print(f"Trained IsolationForest and saved to {MODEL_PATH}")
    return model


def _load_model() -> IsolationForest:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model file not found at {MODEL_PATH}. Train it first by calling train_baseline_detector()."
        )
    with open(MODEL_PATH, "rb") as f:
        model: IsolationForest = pickle.load(f)
    return model


def detect_signal(
    scenario: ScenarioName,
    bus_id: str,
    start_ts: Optional[str] = None,
    end_ts: Optional[str] = None,
) -> DetectionResult:
    """
    Run anomaly detection for a given scenario and bus.

    Inputs:
      - scenario: synthetic scenario name
      - bus_id: e.g. "bus_1"
      - start_ts, end_ts: optional ISO timestamps to window the data

    Output:
      DetectionResult with:
        - timestamps
        - anomaly_scores (higher = more anomalous, using -decision_function)
        - anomaly_flags (1 = anomaly, 0 = normal)
        - summary_score (mean of anomaly_scores)
    """
    df = _load_signals(scenario=scenario, bus_id=bus_id)
    if df.empty:
        raise ValueError(f"No data for scenario={scenario}, bus_id={bus_id}")

    # Optional time window filter
    if start_ts is not None:
        df = df[df["timestamp"] >= start_ts]
    if end_ts is not None:
        df = df[df["timestamp"] <= end_ts]

    if df.empty:
        raise ValueError(
            f"No data for given time window in scenario={scenario}, bus_id={bus_id}"
        )

    model = _load_model()

    X = df[FEATURE_COLUMNS].values
    # IsolationForest.decision_function: higher = less abnormal.
    # We flip the sign so higher == more anomalous, which is easier to reason about.
    raw_scores = model.decision_function(X)
    anomaly_scores = -raw_scores

    # Predict: -1 = anomaly, 1 = normal
    y_pred = model.predict(X)
    anomaly_flags = (y_pred == -1).astype(int)

    summary_score = float(np.mean(anomaly_scores))
    n_points = len(df)
    n_anomalies = int(anomaly_flags.sum())

    return DetectionResult(
        scenario=scenario,
        bus_id=bus_id,
        timestamps=df["timestamp"].astype(str).tolist(),
        anomaly_scores=anomaly_scores.tolist(),
        anomaly_flags=anomaly_flags.tolist(),
        summary_score=summary_score,
        n_points=n_points,
        n_anomalies=n_anomalies,
    )


def detect_signal_payload(
    scenario: ScenarioName,
    bus_id: str,
    start_ts: Optional[str] = None,
    end_ts: Optional[str] = None,
) -> dict:
    """
    Convenience wrapper that runs detect_signal and returns
    a JSON-serializable payload in the standard schema.

    This is the function you should expose as a tool in Goal 3.
    """
    result = detect_signal(
        scenario=scenario,
        bus_id=bus_id,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    return detection_result_to_payload(result)


if __name__ == "__main__":
    # Simple manual test
    train_baseline_detector()
    result = detect_signal("overload_trip", "bus_1")
    print(
        f"Scenario={result.scenario}, bus={result.bus_id}, "
        f"points={result.n_points}, anomalies={result.n_anomalies}, "
        f"summary_score={result.summary_score:.4f}"
    )

    # Optional: show JSON-style payload
    payload = detection_result_to_payload(result)
    print("\nPayload preview:")
    from pprint import pprint
    pprint(payload)
