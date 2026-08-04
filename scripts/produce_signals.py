"""
Signal producer (docs/System_Architecture.md §4.1).

Replays a synthetic scenario CSV onto the raw.signals topic, one reading at a time,
partitioned by bus_id. This is the proof-of-concept stand-in for the live SCADA tap.

As-built, raw.signals feeds ONLY the Streaming service (the live per-bus SSE chart
at /stream/signals). It does NOT trigger detection: the raw.signals -> feeder.events
feature-extraction worker isn't wired to Kafka yet (docs/System_Architecture.md §16),
so detection is driven separately by scripts/produce_events.py over feeder.events.
Run this to make the live chart move; run produce_events.py to produce fault tickets.

Usage:
    .venv/Scripts/python.exe scripts/produce_signals.py --scenario overload_trip --bus_id bus_1
    .venv/Scripts/python.exe scripts/produce_signals.py --scenario overload_trip --rate 50
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kafka import producer, topics  # noqa: E402

NUMERIC = ["voltage_kv", "current_a", "frequency_hz", "temperature_c"]


async def main() -> None:
    p = argparse.ArgumentParser(description="Replay synthetic signals onto raw.signals.")
    p.add_argument("--scenario", default="overload_trip")
    p.add_argument("--bus_id", default=None, help="Limit to one bus (default: all buses).")
    p.add_argument("--rate", type=float, default=20.0, help="Readings per second.")
    p.add_argument("--limit", type=int, default=None, help="Max readings to send.")
    args = p.parse_args()

    csv_path = ROOT / "data" / "synthetic" / f"{args.scenario}.csv"
    if not csv_path.exists():
        raise SystemExit(f"Scenario CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if args.bus_id:
        df = df[df["bus_id"] == args.bus_id]
    df = df.sort_values("timestamp")
    if args.limit:
        df = df.head(args.limit)

    delay = 1.0 / args.rate if args.rate > 0 else 0.0
    sent = 0
    for _, row in df.iterrows():
        reading = {
            "timestamp": str(row["timestamp"]),
            "bus_id": str(row["bus_id"]),
            "scenario": str(row["scenario"]),
            **{c: float(row[c]) for c in NUMERIC},
        }
        await producer.produce(topics.RAW_SIGNALS, reading, key=reading["bus_id"])
        sent += 1
        if sent % 100 == 0:
            print(f"  ...sent {sent} readings")
        if delay:
            await asyncio.sleep(delay)

    print(f"Done. Produced {sent} readings to '{topics.RAW_SIGNALS}'.")


if __name__ == "__main__":
    asyncio.run(main())
