"""
Feature-extraction service handler — THE LIVE BRIDGE (docs/System_Architecture.md §4.2, §16).

This is the link that was missing: nothing consumed `raw.signals` to produce
`feeder.events`, so detection only ever saw pre-reduced rows replayed by
scripts/produce_events.py. Now waveform frames arrive here, accumulate in a
per-feeder `FeatureExtractor`, and a reduced event row is published to
`feeder.events` when a disturbance window closes.

WHAT THIS HANDLER DELIBERATELY DOES NOT DO
------------------------------------------
It does not score. `FeatureExtractor.emit_event()` would — it calls
`publish_event()`, which runs the IsolationForest inline — but detection is a
separate consumer group by design (detection-as-trigger, §4.2). Scoring here as
well would run the model twice per event and put ML work on the ingest path. So
we take the row from `reduce_to_row()` and publish it unscored; `detect.handle`
remains the only place a verdict is formed.

STATE LIVES IN THIS PROCESS
---------------------------
The extractor holds per-bus rolling buffers, so it cannot be shipped to the ML
`ProcessPoolExecutor` the way `score_event_task` is — that pool takes picklable
arguments and discards state between calls. The DSP therefore runs inline, which
is affordable because of the sag gate below.

THE TRIGGER IS LATCHED HERE, NOT IN THE EXTRACTOR
-------------------------------------------------
`cut_window()` in triggered mode fires at "now", so its window always ends
`window_seconds` in the future. A batch caller already holds the whole waveform
and does not care; a live worker would wait forever for a tail that recedes with
every frame. So this handler remembers WHEN the sag started and asks the
extractor for `window_around(that)` once the samples past it have arrived.

That also keeps the DFT off the ingest hot path: each frame already yields its
RMS for the live chart, so cheap per-frame magnitude checks answer "is anything
disturbed?" without touching the per-cycle phasor estimator at all. Two checks,
not one — see the gate constants below for why sag alone misses most faults.
"""

import logging
import time
import uuid
from typing import Any

from backend.kafka import producer, topics, waveform
from ml.feature_extractor import FeatureExtractor

logger = logging.getLogger(__name__)

# ── The gate ────────────────────────────────────────────────────────────────
#
# A frame counts as disturbed if EITHER of these fires. Measured across the
# generated fault classes (worst value over the monitored buses):
#
#     fault       min_Va pu    I unbalance
#     none           0.9993          0.050
#     SLG            0.9950          1.104
#     LL             0.9225          0.706
#     LLG            0.8954          1.149
#     LLL            0.7955          0.015   <- sags, but MORE balanced than healthy
#     LLLG           0.7168          0.014   <- same
#     OPEN_1PH       0.9962          0.505
#     OPEN_2PH       0.9942          0.319
#     OPEN_3PH       0.4989          1.755
#
# Neither test alone is sufficient, and that is the whole point. Unbalanced
# faults — the majority on a distribution feeder — barely move voltage at the
# measuring point. Balanced faults sag hard but are, by definition, balanced:
# their unbalance is LOWER than a healthy feeder's. Gating on sag alone (which
# this handler originally did) silently dropped every SLG, LL, LLG and open
# conductor.
SAG_THRESHOLD = 0.9

# Sits between healthy (0.05) and the mildest fault signature (0.319), with room
# either side for load unbalance that is not a fault.
UNBALANCE_THRESHOLD = 0.20

# Which feeder a bus belongs to. One feeder today; when the topology grows this
# becomes a lookup rather than a constant.
DEFAULT_FEEDER = "ieee13"

# After emitting, ignore new triggers until this many window-lengths have passed.
# One fault produces a sag lasting many cycles, and without this the same
# incident would emit an event on every frame for as long as the sag is
# buffered (§7 makes the same argument for the per-bus hysteresis state machine).
COOLDOWN_WINDOWS = 2.0


class _FeederState:
    """One extractor plus the bookkeeping the streaming trigger needs."""

    def __init__(self, feeder: str) -> None:
        self.extractor = FeatureExtractor(feeder=feeder, mode="triggered")
        # When the current disturbance began, or None if the feeder is quiet.
        self.fired_at: float | None = None
        self.last_emit_t: float = float("-inf")
        self.latest_t: float = float("-inf")


_STATE: dict[str, _FeederState] = {}


def _state_for(feeder: str) -> _FeederState:
    state = _STATE.get(feeder)
    if state is None:
        state = _FeederState(feeder)
        _STATE[feeder] = state
        logger.info(
            "feature extractor ready feeder=%s buses=%s window=%.2fs",
            feeder,
            state.extractor.buses,
            state.extractor.window_seconds,
        )
    return state


def reset_state() -> None:
    """Drop all extractor state. For tests, and for a clean restart."""
    _STATE.clear()


async def handle(frame: dict[str, Any]) -> None:
    feeder = str(frame.get("feeder") or DEFAULT_FEEDER)
    state = _state_for(feeder)
    extractor = state.extractor

    samples = waveform.expand(frame)
    if not samples:
        return

    for sample in samples:
        extractor.ingest(sample)

    state.latest_t = max(state.latest_t, samples[-1]["t"])

    # Latch the trigger on the first disturbed frame — see the module docstring.
    if state.fired_at is None:
        sagging = waveform.min_voltage_pu(frame, extractor.nominal_v) < SAG_THRESHOLD
        unbalanced = (
                waveform.current_unbalance(frame, extractor.low_current_floor)
                > UNBALANCE_THRESHOLD
        )
        if not (sagging or unbalanced):
            return
        if samples[0]["t"] - state.last_emit_t < COOLDOWN_WINDOWS * extractor.window_seconds:
            return  # still inside the previous incident
        state.fired_at = samples[0]["t"]
        logger.info(
            "disturbance latched feeder=%s bus=%s t=%.3f via=%s",
            feeder,
            frame.get("bus_id"),
            state.fired_at,
            "sag" if sagging else "unbalance",
        )

    # Hold until the recovery tail has actually arrived: the window extends past
    # the disturbance so `recovery_Va` is well-defined, and reducing it early
    # would report a recovery that has not happened yet.
    if state.latest_t < state.fired_at + extractor.window_seconds:
        return

    window, t_start, t_end = extractor.window_around(state.fired_at)
    row = extractor.reduce_to_row(window)
    event = {
        "feeder": feeder,
        "timestamp": _iso(t_end),
        "features": row,
        "window_start": _iso(t_start),
        "window_end": _iso(t_end),
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
    }

    await producer.produce(topics.FEEDER_EVENTS, event, key=feeder)

    state.last_emit_t = t_end
    state.fired_at = None
    logger.info(
        "extracted event feeder=%s window=%.3f..%.3f -> feeder.events",
        feeder,
        t_start,
        t_end,
    )


def _iso(t: float) -> str:
    from datetime import UTC, datetime

    try:
        return datetime.fromtimestamp(float(t), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):  # pragma: no cover - clock sanity
        return datetime.fromtimestamp(time.time(), tz=UTC).isoformat()
