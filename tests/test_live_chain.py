"""
The live chain: can an injected waveform become the right diagnosis?

This is the test the demo depends on. It drives synthetic 3-phase waveforms
through the REAL components — extractor gate, DSP reduction, IsolationForest,
supervised classifier — with no Kafka and no containers, and asserts the fault
that went in is the fault that comes out.

WHY IT EXISTS
-------------
Every one of these assertions corresponds to a bug that was live and silent:

  - The waveform generator faulted ONE bus and left the rest at nominal. No
    training scenario looks like that, and the classifier resolved every
    injected fault to OPEN_3PH — an isolated bus beside a healthy feeder being
    the nearest thing it had seen. Fixed by applying a measured whole-feeder
    profile.

  - The extraction handler gated on voltage sag alone. Measured on the testbed,
    an SLG at the feeder head sags to ~0.995 pu, so the gate never fired and
    `raw.signals` produced no events at all. Fixed by adding a sequence-unbalance
    gate beside it.

  - The generator sagged phase A for every fault type, so a BALANCED three-phase
    fault presented as unbalanced and classified as LL. Fixed by giving each
    fault its own sag pattern.

  - `min_Va_fault_pu` reads phase A alone, but the sag pattern applied the
    profile depth to whichever phases the fault named. For LL, LLG and OPEN_2PH
    — which sag B and C — the feature came out 1.0000 against a measured 0.91,
    and `mean_Vunb_fault`, the feature that tells SLG (5.96) from LLG (29.96),
    was not targeted at all. An injected LLG classified as SLG.

  - The cycle a fault steps through has no valid phasor: the phases sit 120
    degrees apart, so the step lands at a different point in each and the DFT
    reports sequence current the feeder never carried. `max_I2_I1_fault` takes
    the peak over the window, so on a balanced fault, whose true ratio is
    ~0.003, the peak WAS the artifact. LLL classified as LLLG.

  - The window ended exactly as the fault cleared, so `recovery_Va_post` — the
    voltage at the window end — reported the sag rather than the recovery, on
    all five buses at once.

None of the three produced an error. The pipeline ran, published, and ticketed —
just with the wrong answer, which is why this asserts on the answer.
"""

import pytest

FAULT_BUS = "b671"
FAULT_START = 1.0
CYCLE = 1.0 / 60.0

# Every class the classifier can emit, all of which now survive the round trip.
CLASSIFIED_CORRECTLY = ["SLG", "LL", "LLG", "LLL", "LLLG", "OPEN_1PH", "OPEN_2PH", "OPEN_3PH"]


def _run(fault: str):
    """Mirror app/kafka/handlers/extract.py: latch on the gate, emit on the tail."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    scripts = root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    import produce_waveforms as pw

    from app.kafka.handlers.extract import SAG_THRESHOLD, UNBALANCE_THRESHOLD
    from app.ml import waveform
    from app.ml.feature_extractor import FeatureExtractor

    fx = FeatureExtractor(feeder="ieee13", mode="triggered")
    fired_at = None
    latest_t = float("-inf")
    row = None

    fault_to = FAULT_START + pw.FAULT_SECONDS

    for c in range(int(3.0 / CYCLE)):
        elapsed = c * CYCLE
        faulted = FAULT_START <= elapsed < fault_to

        for bus in fx.buses:
            frame = pw._frame(
                bus,
                elapsed,
                fault,
                faulted=faulted,
                deepest=(bus == FAULT_BUS),
                recovered=elapsed >= fault_to,
            )
            samples = waveform.expand(frame)
            for sample in samples:
                fx.ingest(sample)
            latest_t = max(latest_t, samples[-1]["t"])

            if fired_at is None:
                sagging = waveform.min_voltage_pu(frame, fx.nominal_v) < SAG_THRESHOLD
                unbalanced = (
                    waveform.current_unbalance(frame, fx.low_current_floor) > UNBALANCE_THRESHOLD
                )
                if sagging or unbalanced:
                    fired_at = samples[0]["t"]

        # Reduce while the window is still buffered — `ingest` prunes older
        # samples, so waiting until the end of the run yields an all-zero row.
        if row is None and fired_at is not None and latest_t >= fired_at + fx.window_seconds:
            window, _, _ = fx.window_around(fired_at)
            row = fx.reduce_to_row(window)

    return fired_at, row


def test_a_healthy_feeder_does_not_trigger():
    """A false positive dispatches a crew to nothing. It matters more than a miss."""
    fired_at, _ = _run("none")
    assert fired_at is None, "healthy feeder tripped the extraction gate"


@pytest.mark.parametrize("fault", CLASSIFIED_CORRECTLY)
def test_injected_fault_is_classified_correctly(fault: str):
    from app.ml.fault_classifier import classify_event
    from app.ml.fault_detector import detect_event

    fired_at, row = _run(fault)

    assert fired_at is not None, f"{fault} never fired the extraction gate"
    assert row is not None, f"{fault} fired but produced no feature row"

    verdict = detect_event(row)
    assert verdict["isFault"], f"{fault} extracted but the detector called it normal"

    classification = classify_event(row)
    assert classification is not None, f"{fault} produced no classification"
    assert classification["fault_type"] == fault, (
        f"injected {fault}, classifier said {classification['fault_type']}"
    )


def test_every_fault_type_produces_a_finite_feature_row():
    """
    Non-finite features are the §11 corruption that biased the original testbed.

    A single inf or nan poisons the whole row: the model receives a value it
    never trained on, for a bus that may not even be faulted.
    """
    import math

    for fault in CLASSIFIED_CORRECTLY:
        _, row = _run(fault)
        assert row is not None
        bad = {k: v for k, v in row.items() if not math.isfinite(v)}
        assert not bad, f"{fault} produced non-finite features: {sorted(bad)}"
