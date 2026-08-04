"""
Event producer (docs/System_Architecture.md §4.1, event path).

Replays pre-reduced per-bus event rows (the testbed feature schema) onto the
feeder.events topic, one feeder snapshot at a time. This is the proof-of-concept
stand-in for the live feature-extraction bridge (app/ml/feature_extractor): its DSP
is implemented, but the streaming worker that would consume raw.signals and publish
reduced rows to feeder.events isn't wired to Kafka yet (docs/System_Architecture.md
§16). So instead of reducing raw 3-phase samples live, we replay rows that are
already in the event schema. It drives the event-detector pipeline:
feeder.events -> detection -> anomalies.detected -> coordinator -> faulttickets.

Usage:
    .venv/Scripts/python.exe scripts/produce_events.py
    .venv/Scripts/python.exe scripts/produce_events.py --csv data/generated/validation_013.csv --rate 2
"""

from __future__ import annotations

import argparse
import asyncio
import math
import numbers
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kafka import producer, topics  # noqa: E402


def _row_features(row: dict) -> dict:
    """JSON-safe copy of the row; non-finite numbers become 0.0 (scoring-safe)."""
    feats: dict = {}
    for c, v in row.items():
        if isinstance(v, numbers.Number) and not isinstance(v, bool):
            fv = float(v)
            feats[c] = fv if math.isfinite(fv) else 0.0
        else:
            feats[c] = str(v)
    return feats


async def main() -> None:
    p = argparse.ArgumentParser(description="Replay event rows onto feeder.events.")
    p.add_argument("--csv", default="data/generated/validation_013.csv")
    p.add_argument("--feeder", default="ieee13")
    p.add_argument("--rate", type=float, default=2.0, help="Events per second.")
    p.add_argument("--limit", type=int, default=None, help="Max events to send.")
    args = p.parse_args()

    csv_path = ROOT / args.csv
    if not csv_path.exists():
        raise SystemExit(f"Event CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if args.limit:
        df = df.head(args.limit)

    delay = 1.0 / args.rate if args.rate > 0 else 0.0
    sent = 0
    for i, (_, row) in enumerate(df.iterrows()):
        d = row.to_dict()
        event = {
            "event_id": str(d.get("scenario_name", f"evt_{i}")),
            "feeder": args.feeder,
            "timestamp": datetime.now(UTC).isoformat(),
            "features": _row_features(d),
            "ground_truth": str(d.get("target_fault_type", "")),
        }
        await producer.produce(topics.FEEDER_EVENTS, event, key=args.feeder)
        sent += 1
        if sent % 100 == 0:
            print(f"  ...sent {sent} events")
        if delay:
            await asyncio.sleep(delay)

    print(f"Done. Produced {sent} events to '{topics.FEEDER_EVENTS}'.")


if __name__ == "__main__":
    asyncio.run(main())
