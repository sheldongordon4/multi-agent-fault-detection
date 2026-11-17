"""
The `raw.signals` waveform frame — one cycle of 3-phase samples for one bus.

WHY A FRAME AND NOT A SAMPLE
----------------------------
The DSP needs instantaneous three-phase waveforms: sequence ratios (I0/I1,
I2/I1) cannot be recovered from a single current magnitude, which is why the old
single-magnitude SCADA reading could never feed detection (docs/System_Architecture.md
Open Decision #6).

Waveforms are dense. At 60 Hz with 32 samples/cycle that is 1,920 samples per
second **per bus** — one Kafka message per sample would be ~65k msg/s across a
34-bus feeder. Batching one cycle per message drops that to ~60 msg/s per bus
(~2k msg/s for the feeder) with no loss of information, because the extractor
groups samples into whole cycles anyway before taking the DFT.

So the wire format is a frame:

    {bus_id, t0, fs, Va[], Vb[], Vc[], Ia[], Ib[], Ic[]}

`expand()` turns it back into the per-sample dicts `FeatureExtractor.ingest`
expects; `rms()` collapses it to the per-cycle magnitudes the live chart plots.
Both consumers of `raw.signals` read the same frame through this one module, so
the two views can never drift apart.
"""

from __future__ import annotations

import math
from typing import Any

CHANNELS = ("Va", "Vb", "Vc", "Ia", "Ib", "Ic")


def expand(frame: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Frame -> the per-sample dicts the feature extractor ingests.

    Timestamps are reconstructed from `t0` and `fs` rather than shipped per
    sample: they are exactly regular by construction, so sending them would
    triple the payload to re-state what the sample rate already says.

    A short or ragged channel truncates the frame rather than raising — a frame
    is transient signal data, and dropping the tail of one cycle is preferable to
    poisoning the stream over it.
    """
    fs = float(frame.get("fs") or 0.0)
    if fs <= 0:
        return []

    t0 = float(frame.get("t0") or 0.0)
    bus = frame.get("bus_id")
    if not bus:
        return []

    channels = {name: frame.get(name) or [] for name in CHANNELS}
    n = min(len(values) for values in channels.values())
    if n == 0:
        return []

    dt = 1.0 / fs
    return [
        {
            "t": t0 + i * dt,
            "bus": bus,
            **{name: float(channels[name][i]) for name in CHANNELS},
        }
        for i in range(n)
    ]


def rms(frame: dict[str, Any]) -> dict[str, float]:
    """
    Frame -> per-channel RMS magnitudes.

    This is what the live chart plots now that `raw.signals` carries waveforms:
    one point per cycle is the same quantity an operator reads off SCADA, and it
    keeps the SSE feed at ~60 values/s per bus instead of ~2k.
    """
    out: dict[str, float] = {}
    for name in CHANNELS:
        values = frame.get(name) or []
        if not values:
            out[f"{name}_rms"] = 0.0
            continue
        total = math.fsum(float(v) * float(v) for v in values)
        out[f"{name}_rms"] = math.sqrt(total / len(values))
    return out


def min_voltage_pu(frame: dict[str, Any], nominal_v: float = 1.0) -> float:
    """
    The deepest phase-voltage RMS in this frame, per unit.

    A cheap sag test the extraction worker can run on every frame, so the
    expensive per-cycle DFT windowing only runs when something is actually
    happening. RMS of a sinusoid is peak/√2, so a 1.0 pu peak reads 0.707 —
    the comparison is normalised here to keep callers in peak-pu terms.
    """
    if nominal_v <= 0:
        return 1.0

    magnitudes = rms(frame)
    phase_rms = [magnitudes[f"{p}_rms"] for p in ("Va", "Vb", "Vc")]
    if not phase_rms or max(phase_rms) == 0.0:
        return 0.0

    return (min(phase_rms) * math.sqrt(2.0)) / nominal_v


def current_unbalance(frame: dict[str, Any], floor: float = 1.0) -> float:
    """
    Cheap per-frame current unbalance, from RMS magnitudes alone.

    A gate, not a measurement. The real sequence decomposition needs per-cycle
    DFT phasors and their angles (FeatureExtractor._sequence); this only needs
    the three RMS values already computed for the live chart, so it can run on
    every frame without putting the DSP on the ingest path.

    Why it is needed at all: voltage sag cannot gate a distribution feeder's
    faults. Measured on the testbed, an SLG at the feeder head sags to ~0.995 pu
    while its sequence ratios move a hundredfold. A sag-only gate ignores every
    unbalanced fault — which is most of them.

    Returns (max - min) / mean over the three phase currents, or 0.0 when the
    feeder is carrying too little current for the ratio to mean anything (the
    same guard _reduce_bus applies before dividing).
    """
    magnitudes = rms(frame)
    phases = [magnitudes[f"I{p}_rms"] for p in ("a", "b", "c")]

    mean = sum(phases) / 3.0
    if mean < floor:
        return 0.0

    return (max(phases) - min(phases)) / mean
