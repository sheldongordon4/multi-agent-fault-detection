"""
feature_extractor.py — the LIVE BRIDGE: raw 3-phase signals -> one event row.

This is the layer that turns a streaming, time-series, multi-phase signal into a
single testbed-format event row (30 features on the 13-bus feeder, 42 on the
34-bus) plus the metadata (feeder, window times, event id) that the model itself
cannot know. The trained event model (ml/event_detector.py) consumes the row;
this class produces it.

Pipeline (see the project notes / docs):
    ingest+buffer   raw per-bus samples into a rolling buffer
     cut_window      decide [t_start, t_end]      -> windowStart / windowEnd
     _phasors        per-cycle phasor estimation  (DSP — NOT IMPLEMENTED)
     _sequence       Fortescue I0/I1/I2           (implemented)
     _reduce_bus     collapse window to 6 features/bus + low-current guard
    metadata        feeder (config) + window times (sample clock) + event id
     emit_event      hand the row + metadata to publish_event()

WHAT IS REAL vs STUBBED
    Real here:   sequence components, pu reduction, low-current guard, row
                 assembly, metadata wiring, publish hand-off.
    Stubbed:     _phasors() (turn raw samples into per-cycle phasors — needs a
                 DFT/Goertzel and a sampling-rate contract) and the triggered
                 windowing detector _detect_disturbance(). Implement those two and
                 the pipeline runs end to end.

CRITICAL: the reductions here MUST match how the testbed produced its features
(window length, per-cycle method, pu base) or the live rows drift out of the
distribution the model trained on. Calibrate against scripts/analyze_testbed.py's
stats_describe_013.csv before trusting live output.
"""

from __future__ import annotations

import cmath
import math
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# Allow `python ml/feature_extractor.py` (script run) to import the ml package.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ml.event_detector import (  # noqa: E402
    FEATURE_FAMILIES,
    load_testbed_model,
    publish_event,
)

# Phase rotation operator a = 1∠120° for the symmetrical-component transform.
_A = cmath.exp(2j * math.pi / 3)


def _buses_from_cols(feature_cols: Sequence[str]) -> List[str]:
    """Recover bus ids (in column order) from a feature-column list."""
    buses: List[str] = []
    for c in feature_cols:
        for fam in FEATURE_FAMILIES:
            pref = fam + "_"
            if c.startswith(pref):
                bus = c[len(pref) :]
                if bus not in buses:
                    buses.append(bus)
    return buses


class FeatureExtractor:
    """
    Streaming extractor: feed it raw per-bus samples, get published events out.

    A "sample" is a dict with a timestamp, a bus id, and the three-phase
    instantaneous (or per-cycle) voltages and currents:
        {"t": <epoch seconds or datetime>, "bus": "b671",
         "Va": .., "Vb": .., "Vc": .., "Ia": .., "Ib": .., "Ic": ..}
    """

    def __init__(
        self,
        feeder: str,
        *,
        buses: Optional[List[str]] = None,
        nominal_v: float = 1.0,
        nominal_hz: float = 60.0,
        window_seconds: float = 0.5,
        low_current_floor: float = 1.0,
        mode: str = "rolling",
        model=None,
        feature_cols: Optional[List[str]] = None,
    ):
        """
        Args:
            feeder:            circuit id written into every event (config, not measured).
            buses:             monitored bus ids in order; defaults to those implied
                               by the model's feature columns.
            nominal_v:         voltage base for per-unit normalization of min_Va/recovery.
            nominal_hz:        system frequency (cycle length = 1/nominal_hz).
            window_seconds:    window length; MUST extend past fault clearing so
                               recovery_Va is well-defined. Calibrate to the testbed.
            low_current_floor: buses whose max current is below this get their
                               sequence ratios forced to ~0 (mirrors the generator's
                               guard against small/small ratio blow-ups).
            mode:              "rolling" (cut every call) or "triggered" (on disturbance).
            model, feature_cols: a preloaded model bundle; else the persisted testbed
                               model is loaded.
        """
        if model is None or feature_cols is None:
            model, feature_cols = load_testbed_model()
        self.model = model
        self.feature_cols = feature_cols
        self.buses = buses or _buses_from_cols(feature_cols)

        self.feeder = feeder
        self.nominal_v = nominal_v
        self.nominal_hz = nominal_hz
        self.window_seconds = window_seconds
        self.low_current_floor = low_current_floor
        self.mode = mode

        #  per-bus rolling buffers of recent samples
        self.buffer: Dict[str, List[dict]] = {b: [] for b in self.buses}

    #  ingest + buffer
    def ingest(self, sample: dict) -> None:
        """Append one raw sample to its bus buffer, pruning anything older than
        the window so the buffer stays bounded."""
        bus = sample["bus"]
        if bus not in self.buffer:
            return  # not a monitored bus
        buf = self.buffer[bus]
        buf.append(sample)
        t_now = sample["t"]
        horizon = t_now - self.window_seconds
        # keep a little slack beyond the window for the trigger / recovery tail
        self.buffer[bus] = [s for s in buf if s["t"] >= horizon - self.window_seconds]

    # choose the window
    def cut_window(self):
        """
        Decide the current window [t_start, t_end] and return the per-bus samples
        inside it, or None if no window is ready.

        Returns: (window: {bus: [samples]}, t_start, t_end) or None.
        """
        if self.mode == "triggered":
            fired_at = self._detect_disturbance()
            if fired_at is None:
                return None
            t_end = fired_at + self.window_seconds  # extend PAST the event for recovery
            t_start = fired_at - self.window_seconds  # a little pre-fault baseline
        elif self.mode == "rolling":
            # newest timestamp across buffers defines "now"
            latest = [b[-1]["t"] for b in self.buffer.values() if b]
            if not latest:
                return None
            t_end = max(latest)
            t_start = t_end - self.window_seconds
        else:
            raise ValueError(f"unknown windowing mode: {self.mode!r}")

        window = {
            bus: [s for s in buf if t_start <= s["t"] <= t_end]
            for bus, buf in self.buffer.items()
        }
        return window, t_start, t_end

    def _detect_disturbance(self):
        """
        TRIGGERED mode only: return the timestamp of a detected disturbance, or
        None. A cheap monitor on RMS deviation / dV/dt / dI/dt belongs here.

        NOT IMPLEMENTED — implement if you choose triggered windowing.
        """
        raise NotImplementedError(
            "triggered windowing needs a disturbance detector; use mode='rolling' "
            "or implement _detect_disturbance()."
        )

    #  per-cycle phasors (DSP — NOT IMPLEMENTED)
    def _phasors(self, bus_samples: List[dict]) -> List[dict]:
        """
        Turn a window of raw samples for ONE bus into a list of per-cycle phasors:
            [{"Va": float_mag, "Vb": float_mag, "Vc": float_mag,
              "Ia": complex,   "Ib": complex,   "Ic": complex}, ...]   one per cycle

        This is the hardware/DSP-specific step: a one-cycle DFT (or Goertzel) at
        nominal_hz over the sampled waveform, which needs a known sampling rate.

        NOT IMPLEMENTED — this is the main thing to fill in. Everything downstream
        (④⑤⑥⑦⑧) is ready and operates on whatever this returns.
        """
        raise NotImplementedError(
            "_phasors(): implement per-cycle phasor estimation (1-cycle DFT/Goertzel "
            "at nominal_hz). It must return voltage magnitudes and complex current "
            "phasors per cycle. Calibrate window/normalization to the testbed."
        )

    # symmetrical components
    @staticmethod
    def _sequence(ia: complex, ib: complex, ic: complex):
        """Fortescue transform: 3-phase current phasors -> (I0, I1, I2)."""
        i0 = (ia + ib + ic) / 3.0
        i1 = (ia + _A * ib + _A * _A * ic) / 3.0
        i2 = (ia + _A * _A * ib + _A * ic) / 3.0
        return i0, i1, i2

    # reduce one bus's window to its 6 features
    def _reduce_bus(self, cycles: List[dict]) -> Dict[str, float]:
        """
        Collapse a bus's per-cycle phasors to its 6 features. Mirrors the testbed
        definitions: voltage families take the extreme/end value, spike families
        take the peak over cycles, with the low-current guard on the ratios.
        """
        va = [c["Va"] / self.nominal_v for c in cycles]
        vb = [c["Vb"] / self.nominal_v for c in cycles]
        vc = [c["Vc"] / self.nominal_v for c in cycles]
        ia_mag = [abs(c["Ia"]) for c in cycles]

        # sequence ratios per cycle (guard tiny positive-sequence denominators)
        i0i1, i2i1 = [], []
        for c in cycles:
            i0, i1, i2 = self._sequence(c["Ia"], c["Ib"], c["Ic"])
            d = abs(i1)
            if d > 1e-9:
                i0i1.append(abs(i0) / d)
                i2i1.append(abs(i2) / d)

        # NEMA-style per-cycle voltage unbalance (%): max deviation from avg / avg
        vunb = []
        for a, b, c in zip(va, vb, vc):
            avg = (a + b + c) / 3.0
            if avg > 1e-9:
                vunb.append(max(abs(a - avg), abs(b - avg), abs(c - avg)) / avg * 100.0)

        max_ia = max(ia_mag) if ia_mag else 0.0
        feats = {
            "min_Va_fault_pu": min(va) if va else 0.0,
            "max_Ia_fault": max_ia,
            "max_I0_I1_fault": max(i0i1) if i0i1 else 0.0,
            "max_I2_I1_fault": max(i2i1) if i2i1 else 0.0,
            "mean_Vunb_fault": (sum(vunb) / len(vunb)) if vunb else 0.0,
            "recovery_Va_post": va[-1] if va else 0.0,  # voltage at window end
        }

        # low-current guard: near-zero-current bus -> ratios are small/small noise
        if max_ia < self.low_current_floor:
            feats["max_I0_I1_fault"] = 0.0
            feats["max_I2_I1_fault"] = 0.0
        return feats

    #  assemble the row in the model's column order
    def reduce_to_row(self, window: Dict[str, List[dict]]) -> Dict[str, float]:
        """Build the {feature_col: value} row for one event across all buses."""
        row: Dict[str, float] = {}
        for bus in self.buses:
            cycles = self._phasors(window.get(bus, []))  # stubbed
            feats = self._reduce_bus(cycles)
            for fam, val in feats.items():
                row[f"{fam}_{bus}"] = val
        return row

    # metadata + publish
    def emit_event(self, window, t_start, t_end) -> dict:
        """Reduce the window to a row, attach metadata, and score+publish it."""
        row = self.reduce_to_row(window)
        return publish_event(
            row,
            feeder=self.feeder,
            timestamp=_iso(t_end),
            window_start=_iso(t_start),
            window_end=_iso(t_end),
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            model=self.model,
            feature_cols=self.feature_cols,
        )

    def step(self) -> Optional[dict]:
        """Convenience: cut a window now and emit an event if one is ready."""
        cut = self.cut_window()
        if cut is None:
            return None
        window, t_start, t_end = cut
        return self.emit_event(window, t_start, t_end)


def _iso(t) -> str:
    """Render a sample timestamp (epoch seconds or datetime) as ISO-8601 UTC."""
    if isinstance(t, datetime):
        return t.astimezone(timezone.utc).isoformat()
    try:
        return datetime.fromtimestamp(float(t), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(t)


if __name__ == "__main__":
    # Readiness summary — instantiation works once a testbed model is trained.
    fx = FeatureExtractor(feeder="ieee13")
    print(f"FeatureExtractor ready for feeder={fx.feeder!r}")
    print(f"  buses        : {fx.buses}")
    print(f"  features     : {len(fx.feature_cols)} ({fx.feature_cols[:2]} ...)")
    print(f"  window_seconds: {fx.window_seconds}  mode: {fx.mode}")
    print(
        "  TODO: implement _phasors() (and _detect_disturbance() for triggered mode)."
    )
