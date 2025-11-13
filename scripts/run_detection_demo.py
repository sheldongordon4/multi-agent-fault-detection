# scripts/run_detection_demo.py

import json
import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path so "ml" can be imported
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ml.baseline_detector import (  # noqa: E402
    detect_signal_payload,
    train_baseline_detector,
)


def main():
    parser = argparse.ArgumentParser(description="Run baseline anomaly detector on synthetic data.")
    parser.add_argument("--scenario", type=str, default="overload_trip")
    parser.add_argument("--bus_id", type=str, default="bus_1")
    args = parser.parse_args()

    # Ensure model exists: train once if missing
    try:
        payload = detect_signal_payload(args.scenario, args.bus_id)
        
        compact_view = {
            "scenario": payload["scenario"],
            "busId": payload["busId"],
            "summary": payload["summary"],
            "anomalyWindows": payload["anomalyWindows"],
            "meta": payload["meta"],
        }
    except FileNotFoundError:
        print("Model not found. Training baseline model first...")
        train_baseline_detector()
        payload = detect_signal_payload(args.scenario, args.bus_id)

    print(json.dumps(compact_view, indent=2))


if __name__ == "__main__":
    main()
