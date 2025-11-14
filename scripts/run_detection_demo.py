# scripts/run_detection_demo.py

import json
import argparse
import sys
from pathlib import Path

import pandas as pd
import numpy as np
from signal_writer import save_signals

# Ensure project root is on sys.path so "ml" can be imported
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ml.baseline_detector import (  # noqa: E402
    detect_signal_payload,
    train_baseline_detector,
)


def build_compact_view(payload: dict) -> dict:
    """
    Build the compact JSON view used by Goal 2/3/4 and
    write a real signal CSV for the Streamlit UI.

    - Uses payload["summary"]["nPoints"] to size the signal.
    - Saves artifacts/signals/demo_signals.csv via save_signals().
    - Adds signalWindowStart, signalWindowEnd, signalMetric to the JSON.
    """

    scenario = payload.get("scenario", "unknown_scenario")
    bus_id = payload.get("busId") or payload.get("bus_id") or "unknown_bus"
    summary = payload.get("summary") or {}
    n_points = summary.get("nPoints")

    # Default values in case something is missing
    signal_window_start = None
    signal_window_end = None
    signal_metric = "current"

    # Only generate & save signals if nPoints is valid
    if isinstance(n_points, int) and n_points > 0:
        # 1-second timestamps, starting at a fixed demo time
        timestamps = pd.date_range(
            start="2025-01-01T00:00:00Z",
            periods=n_points,
            freq="1S",
        ).astype(str)

        # For now, generate a pseudo-real current waveform.
        # LATER: when detect_signal_payload returns actual raw signals,
        #        replace this with the real values.
        values = 150 + 10 * np.sin(np.linspace(0, 20 * np.pi, n_points))

        # Save to CSV so Streamlit can read & plot it as "csv" source
        save_signals(
            timestamps=timestamps,
            values=values,
            metric="current",
            bus_id=bus_id,
            scenario=scenario,
        )

        signal_window_start = timestamps[0]
        signal_window_end = timestamps[-1]
        signal_metric = "current"

    compact_view = {
        "scenario": payload["scenario"],
        "busId": payload["busId"],
        "summary": payload["summary"],
        "anomalyWindows": payload["anomalyWindows"],
        "meta": payload["meta"],
        # NEW: window metadata for Goal 4
        "signalWindowStart": signal_window_start,
        "signalWindowEnd": signal_window_end,
        "signalMetric": signal_metric,
    }

    return compact_view


def main():
    parser = argparse.ArgumentParser(
        description="Run baseline anomaly detector on synthetic data."
    )
    parser.add_argument("--scenario", type=str, default="overload_trip")
    parser.add_argument("--bus_id", type=str, default="bus_1")
    args = parser.parse_args()

    # Ensure model exists: train once if missing
    try:
        payload = detect_signal_payload(args.scenario, args.bus_id)
        compact_view = build_compact_view(payload)
    except FileNotFoundError:
        print("Model not found. Training baseline model first...")
        train_baseline_detector()
        payload = detect_signal_payload(args.scenario, args.bus_id)
        compact_view = build_compact_view(payload)

    print(json.dumps(compact_view, indent=2))


if __name__ == "__main__":
    main()
