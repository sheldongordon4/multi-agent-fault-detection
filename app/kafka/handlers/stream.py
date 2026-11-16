"""
Streaming service handler (docs/System_Architecture.md §4.4).

A separate consumer group on raw.signals, feeding the per-bus rolling buffer and
SSE fan-out behind the UI live chart.

`raw.signals` now carries 3-phase waveform frames rather than scalar SCADA
readings (Open Decision #6), so this handler reduces each frame to its per-cycle
RMS before buffering it (Decision #7). That is deliberate on both counts:

  - pushing ~2k raw samples/s/bus to a browser would swamp the SSE feed, while
    one RMS point per cycle is ~60/s and downsamples cleanly;
  - RMS is the quantity an operator already reads on SCADA, so the chart still
    means what it used to mean.

The DFT-based per-cycle phasors that detection uses are computed separately in
the extraction worker; this is the cheap magnitude view, not a second estimator.
"""

import logging
from datetime import UTC, datetime

from app.ml import waveform
from app.streaming.manager import signal_stream_manager

logger = logging.getLogger(__name__)


def _clock(t0: float | None) -> str:
    """The frame's own sample clock as ISO-8601 — what the chart's x-axis reads.

    Derived from `t0` rather than stamped on arrival: a frame is a measurement,
    and labelling it with the time it happened to be consumed would misplace it
    on the axis whenever the consumer falls behind.
    """
    try:
        return datetime.fromtimestamp(float(t0), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return datetime.now(UTC).isoformat()


async def handle(frame: dict) -> None:
    bus_id = frame.get("bus_id", "unknown_bus")
    t0 = frame.get("t0")

    reading = {
        "timestamp": _clock(t0),
        "bus_id": bus_id,
        "t": t0,
        **waveform.rms(frame),
        "v_pu": waveform.min_voltage_pu(frame),
    }

    await signal_stream_manager.ingest(bus_id, reading)
