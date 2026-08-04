"""
feature_extractor.py — the LIVE BRIDGE: raw 3-phase signals -> one event row.

This is the layer that turns a streaming, time-series, multi-phase signal into a
single testbed-format event row (30 features on the 13-bus feeder, 42 on the
34-bus) plus the metadata (feeder, window times, event id) that the model itself
cannot know. The trained fault model (app/ml/fault_detector.py) consumes the row;
this class produces it.

Pipeline (see the project notes / docs):
    ingest+buffer   raw per-bus samples into a rolling buffer
     cut_window      decide [t_start, t_end]      -> windowStart / windowEnd
     _phasors        per-cycle phasor estimation  (single-bin DFT)
     _sequence       Fortescue I0/I1/I2           (implemented)
     _reduce_bus     collapse window to 6 features/bus + low-current guard
    metadata        feeder (config) + window times (sample clock) + event id
     emit_event      hand the row + metadata to publish_event()

IMPLEMENTATION STATUS
    All stages are implemented end to end: sequence components, pu reduction,
    low-current guard, per-cycle DFT phasors (_phasors), voltage-sag trigger
    (_detect_disturbance), row assembly, metadata wiring, and publish hand-off.
    What remains is the streaming Kafka WORKER that would drive this class off
    raw.signals and publish to feeder.events (docs/System_Architecture.md §16).

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
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

# Allow `python app/ml/feature_extractor.py` (script run) to import the app package.
ROOT_DIR = Path(__file__).resolve().parents[2]  # repo root
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.ml.fault_detector import (  # noqa: E402
    FEATURE_FAMILIES,
    load_testbed_model,
    publish_event,
)

# Phase rotation operator a = 1∠120° for the symmetrical-component transform.
_A = cmath.exp(2j * math.pi / 3)


def _buses_from_cols(feature_cols: Sequence[str]) -> list[str]:
    """Recover bus ids (in column order) from a feature-column list."""
    buses: list[str] = []
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
        buses: list[str] | None = None,
        nominal_v: float = 1.0,
        nominal_hz: float = 60.0,
        window_seconds: float = 0.5,
        low_current_floor: float = 1.0,
        mode: str = "rolling",
        sag_threshold: float = 0.9,
        model=None,
        feature_cols: list[str] | None = None,
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
        # Triggered mode fires when any monitored bus's per-cycle voltage magnitude
        # sags below sag_threshold (in per-unit of nominal_v).
        self.sag_threshold = sag_threshold

        #  per-bus rolling buffers of recent samples
        self.buffer: dict[str, list[dict]] = {b: [] for b in self.buses}

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
            bus: [s for s in buf if t_start <= s["t"] <= t_end] for bus, buf in self.buffer.items()
        }
        return window, t_start, t_end

    def _detect_disturbance(self):
        """
        TRIGGERED mode: return the timestamp of a detected disturbance, or None.

        Cheap monitor: reduce each bus buffer to per-cycle phasors and fire at the
        latest sample if any bus's per-cycle voltage magnitude sags below
        sag_threshold (in per-unit). A deep sag is the strongest single indicator
        of a short-circuit fault; more elaborate dV/dt or dI/dt triggers can layer
        on top of this without changing the windowing contract.
        """
        for buf in self.buffer.values():
            if not buf:
                continue
            cycles = self._phasors(buf)
            if not cycles:
                continue
            vmin = min(min(c["Va"], c["Vb"], c["Vc"]) for c in cycles) / self.nominal_v
            if vmin < self.sag_threshold:
                return buf[-1]["t"]  # fire at "now"
        return None

    #  per-cycle phasors (1-cycle DFT at the fundamental)
    def _phasors(self, bus_samples: list[dict]) -> list[dict]:
        """
        Turn a window of raw samples for ONE bus into a list of per-cycle phasors:
            [{"Va": float_mag, "Vb": float_mag, "Vc": float_mag,
              "Ia": complex,   "Ib": complex,   "Ic": complex}, ...]   one per cycle

        Each sample is a dict with a timestamp `t` and the instantaneous three-phase
        voltages/currents (Va, Vb, Vc, Ia, Ib, Ic). The sampling rate is inferred
        from the median timestamp spacing; samples are grouped into non-overlapping
        one-cycle windows (N = round(fs / nominal_hz)) and each channel's
        fundamental phasor is estimated by a single-bin DFT. Voltages are returned
        as magnitudes (peak amplitude); currents as complex phasors (needed by the
        Fortescue sequence transform in _sequence).

        NOTE: this is a clean textbook estimator. Calibrate the window length and
        pu base to the testbed distribution (stats_describe_013.csv) before trusting
        live output — see the module docstring.
        """
        if len(bus_samples) < 4:
            return []

        s = sorted(bus_samples, key=lambda x: float(x["t"]))
        ts = [float(x["t"]) for x in s]
        dts = sorted(ts[i + 1] - ts[i] for i in range(len(ts) - 1) if ts[i + 1] > ts[i])
        if not dts:
            return []
        dt = dts[len(dts) // 2]  # median spacing
        if dt <= 0:
            return []

        fs = 1.0 / dt
        n_cyc = max(2, int(round(fs / self.nominal_hz)))
        if len(s) < n_cyc:
            return []

        cycles: list[dict] = []
        for start in range(0, len(s) - n_cyc + 1, n_cyc):
            win = s[start : start + n_cyc]
            cyc = {}
            for ch in ("Va", "Vb", "Vc"):
                cyc[ch] = abs(self._dft_phasor([float(w[ch]) for w in win]))
            for ch in ("Ia", "Ib", "Ic"):
                cyc[ch] = self._dft_phasor([float(w[ch]) for w in win])
            cycles.append(cyc)
        return cycles

    @staticmethod
    def _dft_phasor(x: list[float]) -> complex:
        """Single-bin DFT at the fundamental over one cycle -> peak-amplitude phasor."""
        n = len(x)
        if n == 0:
            return 0j
        acc = 0j
        for k in range(n):
            theta = 2.0 * math.pi * k / n
            acc += x[k] * complex(math.cos(theta), -math.sin(theta))
        return (2.0 / n) * acc

    # symmetrical components
    @staticmethod
    def _sequence(ia: complex, ib: complex, ic: complex):
        """Fortescue transform: 3-phase current phasors -> (I0, I1, I2)."""
        i0 = (ia + ib + ic) / 3.0
        i1 = (ia + _A * ib + _A * _A * ic) / 3.0
        i2 = (ia + _A * _A * ib + _A * ic) / 3.0
        return i0, i1, i2

    # reduce one bus's window to its 6 features
    def _reduce_bus(self, cycles: list[dict]) -> dict[str, float]:
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
        for a, b, c in zip(va, vb, vc, strict=False):
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

        # De-energized/islanded buses must report 0, never inf/nan (see
        # docs/System_Architecture.md §11 — the corruption that biased the testbed).
        for k, v in feats.items():
            if not math.isfinite(v):
                feats[k] = 0.0
        return feats

    #  assemble the row in the model's column order
    def reduce_to_row(self, window: dict[str, list[dict]]) -> dict[str, float]:
        """Build the {feature_col: value} row for one event across all buses."""
        row: dict[str, float] = {}
        for bus in self.buses:
            cycles = self._phasors(window.get(bus, []))
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

    def step(self) -> dict | None:
        """Convenience: cut a window now and emit an event if one is ready."""
        cut = self.cut_window()
        if cut is None:
            return None
        window, t_start, t_end = cut
        return self.emit_event(window, t_start, t_end)


def _iso(t) -> str:
    """Render a sample timestamp (epoch seconds or datetime) as ISO-8601 UTC."""
    if isinstance(t, datetime):
        return t.astimezone(UTC).isoformat()
    try:
        return datetime.fromtimestamp(float(t), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return str(t)


if __name__ == "__main__":
    # Readiness summary — instantiation works once a testbed model is trained.
    fx = FeatureExtractor(feeder="ieee13")
    print(f"FeatureExtractor ready for feeder={fx.feeder!r}")
    print(f"  buses        : {fx.buses}")
    print(f"  features     : {len(fx.feature_cols)} ({fx.feature_cols[:2]} ...)")
    print(f"  window_seconds: {fx.window_seconds}  mode: {fx.mode}")
    print("  pipeline     : rolling + triggered modes operational")
