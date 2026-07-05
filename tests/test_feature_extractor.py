"""
Unit tests for the feature-extraction DSP (ml/feature_extractor.py):
the single-bin DFT recovers a known amplitude/phase, per-cycle phasors are correct
on a balanced 3-phase window, and reduced features are always finite (the §11 fix).
"""

import math

from app.ml.feature_extractor import FeatureExtractor

_FAMILIES = [
    "min_Va_fault_pu",
    "max_Ia_fault",
    "max_I0_I1_fault",
    "max_I2_I1_fault",
    "mean_Vunb_fault",
    "recovery_Va_post",
]


def _extractor() -> FeatureExtractor:
    # Dummy model + one-bus feature cols so __init__ doesn't load the trained model.
    feature_cols = [f"{fam}_b1" for fam in _FAMILIES]
    return FeatureExtractor(feeder="test", model=object(), feature_cols=feature_cols, nominal_hz=60.0)


def _sine_window(amp: float, phase: float, n: int) -> list[float]:
    # One full cycle over n samples: theta_k = 2*pi*k/n.
    return [amp * math.cos(2.0 * math.pi * k / n + phase) for k in range(n)]


def test_dft_phasor_recovers_amplitude_and_phase():
    ph = FeatureExtractor._dft_phasor(_sine_window(amp=2.5, phase=0.7, n=32))
    assert abs(abs(ph) - 2.5) < 1e-6
    assert abs(math.atan2(ph.imag, ph.real) - 0.7) < 1e-6


def test_phasors_on_balanced_window():
    ext = _extractor()
    fs, f = 1920.0, 60.0
    n = int(fs / f) * 4  # 4 cycles
    samples = []
    for k in range(n):
        t = k / fs
        wt = 2.0 * math.pi * f * t
        samples.append(
            {
                "t": t,
                "bus": "b1",
                "Va": math.cos(wt),
                "Vb": math.cos(wt - 2 * math.pi / 3),
                "Vc": math.cos(wt + 2 * math.pi / 3),
                "Ia": 100.0 * math.cos(wt),
                "Ib": 100.0 * math.cos(wt - 2 * math.pi / 3),
                "Ic": 100.0 * math.cos(wt + 2 * math.pi / 3),
            }
        )
    cycles = ext._phasors(samples)
    assert len(cycles) >= 3
    c = cycles[0]
    assert abs(c["Va"] - 1.0) < 1e-3
    assert abs(abs(c["Ia"]) - 100.0) < 1e-2


def test_reduced_features_are_finite():
    ext = _extractor()
    # Empty window (de-energized bus) must yield finite zeros, never inf/nan (§11).
    feats = ext._reduce_bus([])
    assert set(feats) == set(_FAMILIES)
    assert all(math.isfinite(v) for v in feats.values())
