"""
Waveform producer — the SCADA/DFR tap stand-in (docs/System_Architecture.md §4.1).

Publishes 3-phase waveform frames to `raw.signals`, one frame per bus per cycle,
which the extraction worker reduces to `feeder.events` and detection then scores.
This is what makes the pipeline live end to end:

    produce_waveforms.py -> raw.signals -> [extraction] -> feeder.events
        -> [detection] -> anomalies.detected -> [coordinator] -> faulttickets
        -> [notification] + [persistence]

It replaces scripts/produce_signals.py for driving detection. That script emits
single-magnitude SCADA readings (`voltage_kv`, `current_a`), which can never feed
the DSP: I0/I1 and I2/I1 need all three phases (Open Decision #6).

FAULT SIGNATURES
----------------
Each fault type is generated from its actual electrical signature, so the
detector and classifier see the sequence-component pattern they were trained on
rather than a generic dip:

    SLG   phase A collapses to ground; large Ia -> strong I0 AND I2
    LL    phases B/C shorted together; no ground path -> I2 but little I0
    LLG   phases B/C to ground -> both I0 and I2
    LLL   all three collapse symmetrically -> deep sag, I0 ~ I2 ~ 0
    LLLG  as LLL with a ground path
    OPEN_1PH  phase A conductor open: its current -> ~0, voltage floats

KNOWN LIMITATION — NO NETWORK PROPAGATION (this is why classification is wrong)
------------------------------------------------------------------------------
Each bus is generated independently: the faulted bus collapses, every other bus
stays at nominal. A real feeder does not behave that way. Measured from
data/generated/validation_013.csv, an SLG at b671 disturbs the WHOLE feeder:

    bus     min_Va   max_Ia   max_I0_I1        vs. what this script emits
    b650     0.997    960.4       0.447        1.000 /  400 / 0.000
    b632     0.975    939.7       0.419        1.000 /  400 / 0.000
    b671     0.939    453.5       0.308        0.250 / 5000 / 0.793  <- faulted
    b684     0.932     72.2       0.211        1.000 /  400 / 0.000
    b675     0.929      0.0       2.029        1.000 /  400 / 0.000

Note the faulted bus is not even the most extreme — b650 carries the most
current, because fault current flows from the source. "One bus dead, four
pristine" matches no training scenario, and the classifier resolves it to
OPEN_3PH: an open conductor is the nearest thing in the training set to a bus
isolated from a healthy feeder.

Consequence: DETECTION works off these waveforms (it only needs "anomalous"),
CLASSIFICATION does not. Fixing it means attenuating the disturbance along the
radial topology (FEEDER_EDGES in the frontend's bus-locations.ts describes it)
rather than applying it to one bus in isolation.

Usage:
    .venv/Scripts/python.exe scripts/produce_waveforms.py --seconds 3 --fault SLG --fault-bus b671
    .venv/Scripts/python.exe scripts/produce_waveforms.py --seconds 10 --fault none
"""

from __future__ import annotations

import argparse
import asyncio
import cmath
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kafka import producer, topics  # noqa: E402
from app.ml.fault_detector import load_testbed_model  # noqa: E402
from app.ml.feature_extractor import _buses_from_cols  # noqa: E402

NOMINAL_HZ = 60.0
FS = 1920.0  # 32 samples/cycle
SAMPLES_PER_CYCLE = int(FS / NOMINAL_HZ)

FAULT_TYPES = ("none", "SLG", "LL", "LLG", "LLL", "LLLG", "OPEN_1PH", "OPEN_2PH", "OPEN_3PH")

# Phase shift per phase, in radians.
_PHASE = {"a": 0.0, "b": -2.0 * math.pi / 3.0, "c": 2.0 * math.pi / 3.0}

# Phase rotation operator a = 1/120deg, for the symmetrical-component synthesis.
_A = cmath.exp(2j * math.pi / 3.0)

# ── The propagation profile ──────────────────────────────────────────────────
#
# MEASURED, not invented: the median value each monitored bus recorded for every
# fault class in data/generated/validation_013.csv. Per bus:
#
#     (min_Va_pu, max_Ia_amps, I0/I1, I2/I1, mean_Vunb_pct, recovery_Va_pu)
#
# This table is the whole reason the generator produces classifiable faults. The
# earlier version faulted one bus and left the rest pristine, which matches no
# training scenario, and the classifier resolved every injected fault to
# OPEN_3PH — an isolated bus beside a healthy feeder being the nearest thing in
# the training set.
#
# Three things in here are counter-intuitive and all three are real:
#
#   - Voltage barely sags. An SLG shows min_Va ~0.995, not the 0.25 a textbook
#     bolted fault suggests. These are feeder-head measurements, not measurements
#     at the fault point.
#   - The faulted bus is not the most extreme. b650 carries the most current
#     because fault current flows FROM the source.
#   - b675 reports max_Ia = 0 under every class, yet its sequence ratios read
#     ~2.0 / ~1.004 when faulted and ~0.0001 when not. A zero phase-A current
#     cannot produce those ratios, so the pair is an artifact of the testbed
#     export rather than a measurement; see KNOWN GAP below.
#
# Two families do the discriminating. The sequence ratios separate ground from
# ungrounded — SLG has I0/I1 ~ 0.36, LL ~0.004 with I2/I1 ~ 0.65, balanced faults
# near zero — and mean_Vunb separates the two ground faults from each other:
# 5.96 for SLG at b671 against 29.96 for LLG. Targeting the ratios but not the
# unbalance is precisely why an injected LLG used to classify as SLG.
BusProfile = tuple[float, float, float, float, float, float]

PROFILE: dict[str, dict[str, BusProfile]] = {
    "SLG": {
        "b650": (0.9975, 523.6, 0.3617, 0.3603, 0.1392, 0.9998),
        "b632": (0.9952, 523.9, 0.3499, 0.3497, 1.5954, 0.9993),
        "b671": (0.9950, 229.1, 0.3676, 0.3683, 5.9572, 0.9993),
        "b684": (0.9955, 42.7, 0.0717, 0.0698, 5.9139, 0.9993),
        "b675": (0.9952, 0.0, 1.9445, 1.0039, 5.9344, 0.9992),
    },
    "LL": {
        "b650": (0.9971, 2135.1, 0.0038, 0.6963, 0.1340, 1.0005),
        "b632": (0.9590, 1701.1, 0.0038, 0.6603, 5.7463, 0.9973),
        "b671": (0.9225, 228.8, 0.0043, 0.5737, 18.6231, 0.9952),
        "b684": (0.9232, 41.3, 0.0044, 0.2103, 19.3140, 0.9969),
        "b675": (0.9246, 0.0, 2.0736, 1.0045, 19.6489, 0.9961),
    },
    "LLG": {
        "b650": (0.9964, 2303.8, 0.3114, 0.4735, 0.1347, 0.9998),
        "b632": (0.9461, 1402.0, 0.3093, 0.4645, 6.2977, 0.9975),
        "b671": (0.9133, 228.9, 0.3038, 0.4575, 29.9635, 0.9947),
        "b684": (0.8954, 41.2, 0.2770, 0.3624, 30.0650, 0.9951),
        "b675": (0.9097, 0.0, 2.2673, 1.0054, 30.0326, 0.9949),
    },
    "LLL": {
        "b650": (0.9951, 3164.4, 0.0027, 0.0026, 0.1332, 1.0000),
        "b632": (0.8978, 3000.6, 0.0027, 0.0029, 0.1512, 0.9942),
        "b671": (0.8436, 217.2, 0.0040, 0.0042, 0.1483, 0.9902),
        "b684": (0.7955, 38.5, 0.0052, 0.0049, 0.1610, 0.9939),
        "b675": (0.8418, 0.0, 2.3492, 1.0049, 0.1755, 0.9922),
    },
    "LLLG": {
        "b650": (0.9964, 3239.0, 0.0027, 0.0027, 0.1340, 0.9999),
        "b632": (0.8769, 3238.6, 0.0027, 0.0026, 0.1391, 0.9962),
        "b671": (0.7507, 1489.4, 0.0034, 0.0035, 0.1741, 0.9892),
        "b684": (0.7168, 34.4, 0.0048, 0.0048, 0.1904, 0.9844),
        "b675": (0.7330, 0.0, 1.8268, 1.0048, 0.1871, 0.9880),
    },
    "OPEN_1PH": {
        "b650": (0.9972, 522.7, 0.0629, 0.0620, 0.1502, 1.0002),
        "b632": (0.9962, 522.7, 0.0627, 0.0625, 0.2272, 1.0001),
        "b671": (0.9980, 228.9, 0.1560, 0.1564, 0.6847, 0.9998),
        "b684": (0.9976, 42.7, 0.1674, 0.1690, 0.7255, 1.0004),
        "b675": (0.9984, 0.0, 2.1974, 1.0042, 49.9213, 0.9999),
    },
    "OPEN_2PH": {
        "b650": (0.9960, 460.1, 0.0468, 0.0477, 0.1404, 0.9994),
        "b632": (0.9994, 460.2, 0.0461, 0.0467, 0.2042, 0.9997),
        "b671": (0.9961, 170.3, 0.1064, 0.1063, 0.4504, 0.9975),
        "b684": (0.9976, 42.7, 0.0085, 0.0081, 0.4749, 0.9985),
        "b675": (0.9942, 0.0, 2.0447, 1.0040, 0.5119, 0.9967),
    },
    "OPEN_3PH": {
        "b650": (0.9972, 452.6, 0.0041, 0.0049, 0.1292, 1.0016),
        "b632": (0.9979, 452.8, 0.0048, 0.0049, 0.1422, 0.9993),
        "b671": (1.0005, 155.6, 0.0059, 0.0052, 0.1406, 0.9984),
        "b684": (0.5005, 9.5, 0.9404, 0.5052, 50.0073, 0.9803),
        "b675": (0.4989, 0.0, 2.0235, 1.0034, 50.0474, 0.9814),
    },
}

NORMAL_PROFILE: dict[str, BusProfile] = {
    "b650": (0.9993, 489.9, 0.0030, 0.0305, 0.1147, 1.0027),
    "b632": (0.9984, 473.0, 0.0030, 0.0159, 0.1991, 1.0014),
    "b671": (0.9995, 163.8, 0.0035, 0.0088, 0.3170, 1.0015),
    "b684": (0.9993, 20.8, 0.0041, 0.0083, 0.4260, 1.0016),
    "b675": (0.9990, 0.0, 0.0001, 0.0001, 0.4455, 1.0014),
}

# Any bus the profile does not name (a different feeder, a retrained model) falls
# back to healthy rather than to zeros, which would read as de-energized.
_DEFAULT: BusProfile = (0.9993, 400.0, 0.0030, 0.0305, 0.2000, 1.0000)


def _profile_for(bus: str, fault: str, faulted: bool) -> BusProfile:
    """
    The target reduced-feature values this bus should exhibit right now.

    Note the profile is applied to EVERY bus while the fault is active, not only
    to `--fault-bus`: a fault is a feeder-wide event, and reproducing that is the
    entire point of this table. `--fault-bus` selects which bus the disturbance
    is centred on for the deepest sag.
    """
    if not faulted or fault == "none":
        return NORMAL_PROFILE.get(bus, _DEFAULT)
    return PROFILE.get(fault, {}).get(bus, NORMAL_PROFILE.get(bus, _DEFAULT))


# Fraction of the extractor's window that is actually in-fault, under the default
# timing (0.5 s fault, 0.5 s window, window centred on the trigger). It matters
# because `mean_Vunb_fault` is a MEAN over the whole window, half of which is
# healthy: to land that mean on the measured median, the in-fault cycles have to
# overshoot it. The window is window_seconds either side of the trigger, so the
# in-fault share is the fault duration over that 1.0 s. Pass a --fault-duration
# other than FAULT_SECONDS and this stops holding.
#
# FAULT_SECONDS is deliberately SHORTER than the extractor's window_seconds
# (0.5): the window has to outlast the fault, or its final cycle is still faulted
# and `recovery_Va_post` — the voltage at the window end — reports the sag
# instead of the recovery.
# Current emitted for a bus the testbed records as carrying none. Must clear
# the extractor's `low_current_floor` (1.0 A), which otherwise discards the
# sequence ratios as small/small noise.
ZERO_CURRENT_FLOOR_A = 1.5

FAULT_SECONDS = 0.3
WINDOW_DUTY = FAULT_SECONDS / (2.0 * 0.5)


def _phase_voltages(
    min_va: float, vunb_pct: float, baseline_vunb_pct: float, a_sags: bool
) -> dict[str, float]:
    """
    Phase amplitudes reproducing BOTH voltage targets this bus was measured at.

    Two features constrain the voltages, and the generator previously honoured
    neither reliably:

      - `min_Va_fault_pu` reads phase A ONLY. The old code applied the profile
        depth to whichever phases SAG_PHASES named, so for LL, LLG and OPEN_2PH —
        which sag B and C — phase A stayed at 1.0 and the feature came out
        1.0000 against a measured 0.91.
      - `mean_Vunb_fault` was not targeted at all, and it is the feature that
        separates the two ground faults: 5.96 for SLG at b671 against 29.96 for
        LLG. Leaving it to fall out of the sag pattern gave LLG a value of 3.1,
        which is far closer to SLG than to LLG.

    Phase A therefore takes the measured minimum outright, and B and C take a
    common value solved from the NEMA unbalance the extractor computes. With
    Vb = Vc = x the deviation on A is always exactly twice that on B or C, so

        U = 200 * |Va - x| / (Va + 2x)

    which inverts to one root above Va and one below. The choice between them is
    physical — is A the faulted phase or the surviving one — and SAG_PHASES
    answers it. Except where a bus disagrees with the fault's nominal pattern:
    OPEN_3PH nominally collapses all three phases, yet b684 measures 50%
    unbalance, so a root outside plausible range falls back to the other one.
    """
    # Undo the window dilution: the mean is over healthy cycles as well as
    # faulted ones, so the faulted cycles must carry more than the target.
    u = (vunb_pct - (1.0 - WINDOW_DUTY) * baseline_vunb_pct) / WINDOW_DUTY
    # The 'above' root is asymptotic at U=100 and the 'below' root at U=200;
    # clamping keeps a measurement at the asymptote from producing an infinity.
    u = min(max(u, 0.0), 199.0)

    def root(above: bool) -> float:
        if above:  # A is depressed, B and C sit higher than it
            denom = 200.0 - 2.0 * u
            return min_va * (200.0 + u) / denom if denom > 1e-6 else float("inf")
        return min_va * (200.0 - u) / (200.0 + 2.0 * u)

    x = root(a_sags)
    if not 0.0 <= x <= 1.5:
        x = root(not a_sags)
    return {"a": min_va, "b": min(max(x, 0.0), 1.5), "c": min(max(x, 0.0), 1.5)}


def _phase_currents(mag: float, r0: float, r2: float) -> dict[str, complex]:
    """
    Three phase currents whose symmetrical components hit the target ratios.

    Built the way the extractor takes them apart: compose from sequence
    components, and its Fortescue transform recovers I0/I1 and I2/I1 exactly.
    Synthesising phase currents directly and hoping the ratios come out right is
    what produced all-zero sequence ratios before.
    """
    if mag <= 0.0:
        # b675 reports max_Ia = 0 in every testbed row, yet the same rows carry
        # I0/I1 ~ 2.0 when faulted against ~0.0001 when not — a near-binary
        # fault flag. Both cannot be literally true: a zero phase-A current
        # cannot have a sequence ratio, so the pair is an export artifact.
        #
        # Emitting zeros honours max_Ia and loses the ratios, because the
        # extractor's low-current guard zeroes any bus below its floor. Emitting
        # at the floor honours the ratios and puts 1.5 A on a column whose real
        # values are all 0. The ratios are worth more: they are two of the six
        # features that separate a faulted feeder from a healthy one at this
        # bus, and 1.5 A beside b650's 3000 A is nothing.
        mag = ZERO_CURRENT_FLOOR_A

    i1 = 1.0 + 0j
    i0 = r0 * i1
    i2 = r2 * i1

    ia = i1 + i2 + i0
    ib = _A * _A * i1 + _A * i2 + i0
    ic = _A * i1 + _A * _A * i2 + i0

    scale = mag / abs(ia) if abs(ia) > 0 else 0.0
    return {"a": ia * scale, "b": ib * scale, "c": ic * scale}



# Which phases each fault depresses. The profile supplies the sag DEPTH; this
# supplies the PATTERN, and the pattern is what the classifier reads as balance.
#
# Getting this wrong is subtle and fatal: sagging only phase A for every fault
# made a balanced three-phase fault look unbalanced, so LLL and LLLG were
# classified as LL. A balanced fault must depress all three phases TOGETHER —
# that near-zero voltage unbalance is its defining signature, not an accident.
SAG_PHASES: dict[str, tuple[str, ...]] = {
    "SLG": ("a",),            # A to ground
    "LL": ("b", "c"),         # B-C short
    "LLG": ("b", "c"),        # B-C to ground
    "LLL": ("a", "b", "c"),   # balanced
    "LLLG": ("a", "b", "c"),  # balanced
    "OPEN_1PH": ("a",),
    "OPEN_2PH": ("b", "c"),
    "OPEN_3PH": ("a", "b", "c"),
}


def _frame(
    bus: str, t0: float, fault: str, faulted: bool, deepest: bool, recovered: bool = False
) -> dict:
    """
    One cycle of 3-phase samples for one bus, as a `raw.signals` frame.

    Built backwards from the target reduced features rather than forwards from a
    physical fault model: the profile says what this bus should measure, and the
    waveform is synthesised to produce exactly that once the extractor reduces
    it. That keeps the live rows inside the distribution the classifier trained
    on, which forward-simulating a fault on one bus did not.
    """
    min_va, max_ia, r0, r2, vunb, recovery = _profile_for(bus, fault, faulted)

    # Depth AND unbalance from the profile; SAG_PHASES now only says which side
    # of the unbalance phase A falls on. `deepest` is carried for readability at
    # the call site — the profile already encodes each bus's own depth, so the
    # faulted bus needs no extra treatment here.
    faulting = faulted and fault != "none"
    if faulting:
        # The healthy cycles sharing this window are emitted balanced (below),
        # so the window mean is exactly WINDOW_DUTY x the in-fault unbalance.
        vunb_target, baseline = vunb, 0.0
    elif fault == "none":
        # Nothing to dilute: every cycle in the window is a healthy one, so the
        # bus emits the NO_FAULT unbalance it was measured at.
        vunb_target = baseline = vunb
    else:
        # Pre- and post-fault cycles of a fault run, emitted perfectly balanced:
        # zero voltage unbalance and zero sequence content. This is the one
        # place the generator departs from the feeder's real behaviour, and it
        # is deliberate. The testbed reduced each feature over the fault window
        # alone; this extractor's window straddles the event, and `mean_Vunb`
        # is a MEAN while `max_I2_I1` is a MAX, so healthy cycles either dilute
        # a target or overwrite it. Both bite on the balanced faults, whose
        # measured values sit BELOW the healthy baseline — LLL reads 0.15%
        # unbalance against a healthy 0.32%, and I2/I1 of 0.0026 at b650
        # against a healthy 0.0305. Leaving the healthy half realistic makes
        # those numbers unreachable no matter how the faulted half is shaped.
        vunb_target = baseline = 0.0
        r0 = r2 = 0.0
        if recovered:
            # `recovery_Va_post` is the phase-A magnitude of the LAST cycle in
            # the window, so it is read from these post-fault frames and from
            # nowhere else. A feeder does not come back to exactly nominal —
            # LLLG leaves b684 at 0.9844 — and emitting a flat 1.0 put all five
            # of these features on the healthy side of the split.
            min_va = _profile_for(bus, fault, faulted=True)[5]
    voltages = _phase_voltages(min_va, vunb_target, baseline, "a" in SAG_PHASES.get(fault, ()))

    currents = _phase_currents(max_ia, r0, r2)

    channels: dict[str, list[float]] = {c: [] for c in ("Va", "Vb", "Vc", "Ia", "Ib", "Ic")}
    for k in range(SAMPLES_PER_CYCLE):
        t = t0 + k / FS
        wt = 2.0 * math.pi * NOMINAL_HZ * t
        for phase in ("a", "b", "c"):
            tag = phase
            channels[f"V{tag}"].append(voltages[phase] * math.cos(wt + _PHASE[phase]))
            # Carry the synthesised phase angle through, not just the magnitude —
            # the angles ARE the sequence content the extractor decomposes.
            i = currents[phase]
            channels[f"I{tag}"].append(abs(i) * math.cos(wt + cmath.phase(i)))

    return {
        "bus_id": bus,
        "t0": t0,
        "fs": FS,
        **channels,
    }


async def main() -> None:
    p = argparse.ArgumentParser(description="Publish 3-phase waveform frames to raw.signals.")
    p.add_argument("--feeder", default="ieee13")
    p.add_argument("--seconds", type=float, default=3.0, help="Seconds of waveform to send.")
    p.add_argument(
        "--fault",
        default="SLG",
        choices=FAULT_TYPES,
        help="Fault to inject, or 'none' for a healthy feeder.",
    )
    p.add_argument("--fault-bus", default=None, help="Bus to fault (default: a middle bus).")
    p.add_argument(
        "--fault-start",
        type=float,
        default=1.0,
        help="Seconds of healthy waveform before the fault begins.",
    )
    p.add_argument(
        "--fault-duration",
        type=float,
        default=FAULT_SECONDS,
        help=(
            "Fault duration in seconds; the feeder recovers afterwards. Must stay "
            "below the extractor's window_seconds or the window ends before the "
            "fault clears and recovery_Va_post reads the sag instead."
        ),
    )
    p.add_argument(
        "--realtime",
        action="store_true",
        help="Pace output at wall-clock speed instead of sending as fast as possible.",
    )
    args = p.parse_args()

    _, feature_cols = load_testbed_model()
    buses = _buses_from_cols(feature_cols)
    if not buses:
        raise SystemExit("No buses found in the model's feature columns — train the model first.")

    fault_bus = args.fault_bus or buses[len(buses) // 2]
    if args.fault != "none" and fault_bus not in buses:
        raise SystemExit(f"--fault-bus {fault_bus!r} is not monitored; choose from {buses}")

    cycle_seconds = 1.0 / NOMINAL_HZ
    n_cycles = int(args.seconds / cycle_seconds)
    t0 = time.time()

    fault_from = args.fault_start
    fault_to = args.fault_start + args.fault_duration

    print(
        f"feeder={args.feeder} buses={len(buses)} fault={args.fault}"
        f"{'' if args.fault == 'none' else f' on {fault_bus}'} "
        f"cycles={n_cycles} ({args.seconds:.1f}s @ {FS:.0f} Hz)"
    )

    sent = 0
    for cycle in range(n_cycles):
        elapsed = cycle * cycle_seconds
        faulted_now = args.fault != "none" and fault_from <= elapsed < fault_to

        for bus in buses:
            # The fault profile is applied to EVERY bus, not just --fault-bus.
            # A feeder fault is a feeder-wide event: the source bus carries the
            # most current, remote buses see attenuated sequence content, and it
            # is that whole-feeder pattern the classifier was trained on.
            # Faulting one bus in isolation is what made every injected fault
            # come out as OPEN_3PH.
            frame = _frame(
                bus,
                t0 + elapsed,
                args.fault,
                faulted=faulted_now,
                deepest=(bus == fault_bus),
                recovered=elapsed >= fault_to,
            )
            frame["feeder"] = args.feeder
            # Partition by bus so each bus's frames stay in order (§7).
            await producer.produce(topics.RAW_SIGNALS, frame, key=bus)
            sent += 1

        if args.realtime:
            await asyncio.sleep(cycle_seconds)

    # NOTE: app/kafka/producer.produce() flushes on every call, so a large run
    # here is dominated by that round trip rather than by generation. Fine for a
    # dev driver; a real SCADA tap would want a batched producer.
    print(f"Done. Produced {sent} frames to '{topics.RAW_SIGNALS}'.")


if __name__ == "__main__":
    asyncio.run(main())
