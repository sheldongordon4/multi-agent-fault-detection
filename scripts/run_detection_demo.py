"""Run the legacy baseline anomaly detector and emit a compact demo payload."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from signal_writer import save_signals

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.ml.baseline_detector import (  # noqa: E402
    detect_signal_payload,
    train_baseline_detector,
)


def build_compact_view(payload: dict) -> dict:
    """Build the compact JSON view used by the local demo and save the signal CSV."""
    scenario = payload.get("scenario", "unknown_scenario")
    bus_id = payload.get("busId") or payload.get("bus_id") or "unknown_bus"
    summary = payload.get("summary") or {}
    n_points = summary.get("nPoints")

    signal_window_start = None
    signal_window_end = None
    signal_metric = "current"

    if isinstance(n_points, int) and n_points > 0:
        timestamps = pd.date_range(
            start="2025-01-01T00:00:00Z",
            periods=n_points,
            freq="1s",
        ).astype(str)

        values = 150 + 10 * np.sin(np.linspace(0, 20 * np.pi, n_points))
        save_signals(
            timestamps=timestamps,
            values=values,
            metric="current",
            bus_id=bus_id,
            scenario=scenario,
        )
        signal_window_start = timestamps[0]
        signal_window_end = timestamps[-1]

    return {
        "scenario": payload["scenario"],
        "busId": payload["busId"],
        "summary": payload["summary"],
        "anomalyWindows": payload["anomalyWindows"],
        "meta": payload["meta"],
        "signalWindowStart": signal_window_start,
        "signalWindowEnd": signal_window_end,
        "signalMetric": signal_metric,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run baseline anomaly detector on synthetic data.")
    parser.add_argument("--scenario", type=str, default="overload_trip")
    parser.add_argument("--bus_id", type=str, default="bus_1")
    args = parser.parse_args()

    try:
        payload = detect_signal_payload(args.scenario, args.bus_id)
    except FileNotFoundError:
        print("Model not found. Training baseline model first...")
        train_baseline_detector()
        payload = detect_signal_payload(args.scenario, args.bus_id)

    compact_view = build_compact_view(payload)
    print(json.dumps(compact_view, indent=2))


if __name__ == "__main__":
    main()
