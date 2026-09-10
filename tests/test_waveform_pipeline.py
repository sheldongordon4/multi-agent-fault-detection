"""
The live bridge: raw.signals waveform frames -> feeder.events -> a FaultTicket.

Three layers, cheapest first:

  1. `waveform` — the wire format itself (expand / rms / sag gate).
  2. `extract.handle` — the worker that was missing, with the producer faked so
     no broker is needed.
  3. THE CHAIN TEST — waveform samples driven through the real FeatureExtractor,
     the real detector, the real classifier and the real coordinator, asserting a
     valid FaultTicket comes out the far end.

(3) is the one that matters. Until now the pipeline was only ever exercised in
pieces — produce_events.py replayed pre-reduced rows straight onto feeder.events,
so nothing proved that a signal could become a ticket. Each stage's contract with
the next is now pinned by a test that fails if any of them drifts.
"""

import math

import pytest

from app.ml import waveform

NOMINAL_HZ = 60.0
FS = 1920.0
SAMPLES_PER_CYCLE = int(FS / NOMINAL_HZ)

_PHASE = {"a": 0.0, "b": -2.0 * math.pi / 3.0, "c": 2.0 * math.pi / 3.0}


def make_frame(
    bus: str,
    t0: float,
    *,
    v_pu: dict[str, float] | None = None,
    i_amps: dict[str, float] | None = None,
) -> dict:
    """One cycle of 3-phase samples, defaulting to a healthy balanced bus."""
    v_pu = v_pu or {"a": 1.0, "b": 1.0, "c": 1.0}
    i_amps = i_amps or {"a": 400.0, "b": 400.0, "c": 400.0}

    channels: dict[str, list[float]] = {c: [] for c in waveform.CHANNELS}
    for k in range(SAMPLES_PER_CYCLE):
        wt = 2.0 * math.pi * NOMINAL_HZ * (t0 + k / FS)
        for phase in ("a", "b", "c"):
            angle = wt + _PHASE[phase]
            channels[f"V{phase}"].append(v_pu[phase] * math.cos(angle))
            channels[f"I{phase}"].append(i_amps[phase] * math.cos(angle))

    return {"bus_id": bus, "t0": t0, "fs": FS, **channels}


# ── 1. the wire format ───────────────────────────────────────────────────────


def test_expand_reconstructs_a_regular_sample_clock():
    """Timestamps are derived from t0 + fs, not shipped — so they must be exact."""
    frame = make_frame("b671", 10.0)
    samples = waveform.expand(frame)

    assert len(samples) == SAMPLES_PER_CYCLE
    assert samples[0]["t"] == pytest.approx(10.0)
    assert samples[1]["t"] - samples[0]["t"] == pytest.approx(1.0 / FS)
    assert samples[0]["bus"] == "b671"
    # The extractor keys on "bus"/"t"; the wire uses "bus_id". If that mapping
    # breaks, every frame is silently dropped as an unmonitored bus.
    assert set(waveform.CHANNELS) <= set(samples[0])


def test_expand_truncates_a_ragged_frame_rather_than_raising():
    """Transient signal data: lose the tail of a cycle, never poison the stream."""
    frame = make_frame("b671", 0.0)
    frame["Ic"] = frame["Ic"][:5]

    samples = waveform.expand(frame)
    assert len(samples) == 5


@pytest.mark.parametrize(
    "frame",
    [
        {"bus_id": "b671", "t0": 0.0, "fs": 0.0},  # no sample rate
        {"t0": 0.0, "fs": FS},  # no bus
        {"bus_id": "b671", "t0": 0.0, "fs": FS},  # no channels
    ],
)
def test_expand_returns_nothing_for_an_unusable_frame(frame):
    assert waveform.expand(frame) == []


def test_rms_recovers_the_amplitude_of_a_known_sinusoid():
    frame = make_frame("b671", 0.0, i_amps={"a": 1000.0, "b": 1000.0, "c": 1000.0})
    magnitudes = waveform.rms(frame)

    # RMS of a pure sinusoid is peak / sqrt(2).
    assert magnitudes["Va_rms"] == pytest.approx(1.0 / math.sqrt(2), rel=1e-3)
    assert magnitudes["Ia_rms"] == pytest.approx(1000.0 / math.sqrt(2), rel=1e-3)


def test_sag_gate_separates_a_healthy_feeder_from_a_faulted_one():
    """The cheap per-frame check that keeps the DFT off the ingest hot path."""
    healthy = waveform.min_voltage_pu(make_frame("b671", 0.0))
    faulted = waveform.min_voltage_pu(make_frame("b671", 0.0, v_pu={"a": 0.25, "b": 1.0, "c": 1.0}))

    assert healthy == pytest.approx(1.0, rel=1e-3)
    assert faulted == pytest.approx(0.25, rel=1e-3)
    assert faulted < 0.9 <= healthy


# ── 2. the extraction worker ─────────────────────────────────────────────────


@pytest.fixture
def captured_events(monkeypatch):
    """Collect what the handler would publish, instead of reaching a broker."""
    from app.kafka import handlers
    from app.kafka.handlers import extract

    extract.reset_state()
    published: list[tuple[str, dict]] = []

    async def _fake_produce(topic, payload, key=None):
        published.append((topic, payload))

    monkeypatch.setattr(extract.producer, "produce", _fake_produce)
    assert handlers  # keep the import meaningful for collection ordering
    yield published
    extract.reset_state()


async def _drive(handler, buses, *, seconds: float, fault_bus: str | None, fault_from: float):
    """Feed `seconds` of waveform through the handler, faulting one bus midway."""
    cycle = 1.0 / NOMINAL_HZ
    for c in range(int(seconds / cycle)):
        t = c * cycle
        for bus in buses:
            faulted = fault_bus is not None and bus == fault_bus and t >= fault_from
            frame = make_frame(
                bus,
                t,
                v_pu={"a": 0.25, "b": 1.0, "c": 1.0} if faulted else None,
                i_amps={"a": 5000.0, "b": 400.0, "c": 400.0} if faulted else None,
            )
            await handler(frame)


async def test_healthy_waveform_publishes_nothing(captured_events):
    """A quiet feeder must not emit an event per window — the sag gate holds."""
    from app.kafka.handlers import extract

    buses = extract._state_for("ieee13").extractor.buses[:3]
    await _drive(extract.handle, buses, seconds=1.5, fault_bus=None, fault_from=0.0)

    assert captured_events == []


async def test_a_fault_publishes_one_feeder_event(captured_events):
    """
    The link that did not exist: waveforms in, a reduced event row out.

    Also pins the cooldown — a sag lasts many cycles, and without it the same
    incident would re-emit on every frame for as long as it stayed buffered.
    """
    from app.kafka import topics
    from app.kafka.handlers import extract

    buses = extract._state_for("ieee13").extractor.buses[:3]
    await _drive(extract.handle, buses, seconds=3.0, fault_bus=buses[0], fault_from=0.5)

    assert captured_events, "a sustained fault produced no feeder.events message"

    topic, event = captured_events[0]
    assert topic == topics.FEEDER_EVENTS
    assert event["feeder"] == "ieee13"
    assert event["features"], "the event carries no reduced feature row"
    assert event["window_start"] < event["window_end"]

    # One incident, not one per frame.
    assert len(captured_events) <= 2, f"cooldown failed: {len(captured_events)} events"


async def test_published_row_matches_the_model_feature_schema(captured_events):
    """
    The row has to be in the model's column space or detection silently degrades.

    This is the seam the whole bridge rests on: the extractor builds columns from
    the model's own feature list, so a mismatch here means the DSP and the model
    have drifted apart.
    """
    from app.kafka.handlers import extract
    from app.ml.fault_detector import load_testbed_model

    _, feature_cols = load_testbed_model()

    buses = extract._state_for("ieee13").extractor.buses[:3]
    await _drive(extract.handle, buses, seconds=3.0, fault_bus=buses[0], fault_from=0.5)
    assert captured_events

    row = captured_events[0][1]["features"]
    assert set(row) <= set(feature_cols)
    assert all(isinstance(v, float) and math.isfinite(v) for v in row.values()), (
        "non-finite features would poison the detector (§11)"
    )


# ── 3. the chain: signal -> ticket ───────────────────────────────────────────


async def test_waveform_becomes_a_fault_ticket(captured_events):
    """
    THE end-to-end contract test.

    Runs the real stages in-process — FeatureExtractor -> IsolationForest ->
    RandomForest classifier -> coordinator -> FaultTicket — with no broker and no
    LLM (the coordinator's offline heuristic path). If any stage's output stops
    matching the next stage's input, this fails.
    """
    from app.faults.schemas import FaultTicket
    from app.faults.service import run_fault_diagnosis
    from app.kafka.handlers import extract
    from app.ml.scoring import classify_event_task, score_event_task

    buses = extract._state_for("ieee13").extractor.buses[:3]
    await _drive(extract.handle, buses, seconds=3.0, fault_bus=buses[0], fault_from=0.5)
    assert captured_events, "extraction produced nothing to detect on"

    event = captured_events[0][1]

    # Stage 2 — detection.
    detection = score_event_task(
        event["features"],
        feeder=event["feeder"],
        timestamp=event["timestamp"],
        event_id=event["event_id"],
    )
    assert "verdict" in detection
    assert detection["topBuses"], "detection reported no disturbed buses to diagnose"

    # Stage 3 — classification is optional enrichment and must never block.
    classification = classify_event_task(event["features"])
    if classification is not None:
        detection["classification"] = classification

    # Stage 4 — the coordinator.
    detection["incident_id"] = event["event_id"]
    ticket = run_fault_diagnosis(detection)

    # Stage 5 — the contract the frontend and persistence both depend on.
    validated = FaultTicket.model_validate(ticket)
    assert validated.bus_id
    assert validated.fault_type
    assert validated.summary
    assert validated.recommended_actions
