"""
LIVE event producer (docs/System_Architecture.md §4.1/§4.2, real bridge).

Unlike scripts/produce_events.py (which replays pre-reduced rows), this exercises
the *live* path end-to-end: it generates raw 3-phase waveform samples, runs them
through ml.feature_extractor.FeatureExtractor (now with a real 1-cycle DFT), and
publishes the reduced per-bus event row to feeder.events for the detection service.

The waveform generator is a simple, plausibly-scaled synthetic source:
  - normal buses: balanced 3-phase, ~1.0 pu voltage, moderate balanced current
  - faulted bus (SLG on phase A): deep sag on Va + large Ia, which creates the
    zero-/negative-sequence signature the detector keys on.

CALIBRATION CAVEAT: the reduced features are only approximately on the testbed
scale. Exact alignment to the training distribution (currents, correlations) is a
tuning step — see the feature_extractor module docstring and §11.

Usage:
    .venv/Scripts/python.exe scripts/produce_events_live.py --n 20 --fault-prob 0.4
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kafka import producer, topics  # noqa: E402
from app.ml.fault_detector import load_testbed_model, train_isoforest_on_testbed  # noqa: E402
from app.ml.feature_extractor import FeatureExtractor  # noqa: E402

NOMINAL_HZ = 60.0
FS = 1920.0  # 32 samples/cycle
SECONDS = 0.5
NORMAL_I = 400.0  # balanced load current (roughly testbed-scale)
FAULT_I = 5000.0  # phase-A fault current
FAULT_SAG = 0.35  # Va sag depth (pu) on the faulted phase


def _bus_samples(bus: str, t0: float, *, faulted: bool) -> list[dict]:
    """One window of raw 3-phase samples for a bus (SLG phase-A fault if faulted)."""
    n = int(FS * SECONDS)
    va, ia = (FAULT_SAG, FAULT_I) if faulted else (1.0, NORMAL_I)
    out = []
    for k in range(n):
        t = t0 + k / FS
        wt = 2.0 * math.pi * NOMINAL_HZ * t
        out.append(
            {
                "t": t,
                "bus": bus,
                "Va": va * math.cos(wt),
                "Vb": 1.0 * math.cos(wt - 2 * math.pi / 3),
                "Vc": 1.0 * math.cos(wt + 2 * math.pi / 3),
                "Ia": ia * math.cos(wt),
                "Ib": NORMAL_I * math.cos(wt - 2 * math.pi / 3),
                "Ic": NORMAL_I * math.cos(wt + 2 * math.pi / 3),
            }
        )
    return out


def _make_event(ext: FeatureExtractor, fault_bus: str | None, t0: float) -> dict:
    """Generate a window across all buses, reduce it to an event row via the DSP."""
    ext.buffer = {b: [] for b in ext.buses}
    for bus in ext.buses:
        for s in _bus_samples(bus, t0, faulted=(bus == fault_bus)):
            ext.ingest(s)
    cut = ext.cut_window()
    window, _t_start, _t_end = cut
    row = ext.reduce_to_row(window)
    return {
        "event_id": f"live_{uuid.uuid4().hex[:10]}",
        "feeder": ext.feeder,
        "timestamp": datetime.now(UTC).isoformat(),
        "features": row,
        "ground_truth": "SLG" if fault_bus else "NO_FAULT",
    }


async def main() -> None:
    p = argparse.ArgumentParser(description="Produce live-extracted events to feeder.events.")
    p.add_argument("--feeder", default="ieee13")
    p.add_argument("--n", type=int, default=10, help="Number of events to emit.")
    p.add_argument("--fault-prob", type=float, default=0.4, help="P(event is a fault).")
    p.add_argument("--rate", type=float, default=1.0, help="Events per second.")
    args = p.parse_args()

    try:
        model, feature_cols = load_testbed_model()
    except FileNotFoundError:
        train_isoforest_on_testbed("data/generated/normal_train_013.csv")
        model, feature_cols = load_testbed_model()

    ext = FeatureExtractor(feeder=args.feeder, model=model, feature_cols=feature_cols)
    delay = 1.0 / args.rate if args.rate > 0 else 0.0

    for i in range(args.n):
        fault_bus = random.choice(ext.buses) if random.random() < args.fault_prob else None
        event = _make_event(ext, fault_bus, t0=float(i))
        await producer.produce(topics.FEEDER_EVENTS, event, key=args.feeder)
        print(f"  sent {event['event_id']} ground_truth={event['ground_truth']} bus={fault_bus}")
        if delay:
            await asyncio.sleep(delay)

    print(f"Done. Produced {args.n} live events to '{topics.FEEDER_EVENTS}'.")


if __name__ == "__main__":
    asyncio.run(main())
