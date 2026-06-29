"""
generate_normal_data.py — generate NORMAL operating data for the IsolationForest,
informed by the fault testbed data.

The fault CSVs contain no "normal" rows, but they DO contain normal *values* at the
buses that each fault left electrically unaffected (voltage ~1.0 pu, small sequence
ratios, low unbalance) plus the post-fault recovery columns. This script:

  1. Estimates a per-bus "normal envelope" (mean + spread) for each of the 6
     fault-signature features, by harvesting the CALM tail of each column:
       - voltage-like features (min_Va, recovery): the HIGH tail  (faults push DOWN)
       - spike-like features (max_Ia, I0/I1, I2/I1, Vunb): the LOW tail (faults push UP)
  2. Estimates the inter-feature / inter-bus CORRELATION from the calmest rows
     (the least-disturbed snapshots), and samples synthetic NORMAL rows from a
     CORRELATED multivariate-normal envelope (Cov = D R D). This replaces the v1
     independent per-feature sampling, so generated normal preserves the real
     couplings (same-bus V<->recovery and I0/I1<->I2/I1, cross-bus voltage moves).
  3. Optionally injects REAL fault rows from the source CSV at a controlled ratio,
     so you get a labelled set for validation.

numpy is an OPTIONAL accelerator: if it is importable the correlated path is used;
otherwise the script falls back to the v1 independent `gauss` sampler so it still
runs on a pure-stdlib interpreter. Use --independent to force the v1 behaviour.

Output uses the SAME schema as the testbed CSV (so scripts/load_testbed.py reads it
unchanged), with target_fault_type = NO_FAULT on the normal rows.

Examples:
    # pure normal training set (no faults), correlated sampling
    python scripts/generate_normal_data.py --csv "<fault.csv>" --n-normal 4000 \
        --fault-ratio 0 --out data/generated/normal_train.csv

    # validation set: ~10% real faults mixed into normal
    python scripts/generate_normal_data.py --csv "<fault.csv>" --n-normal 2000 \
        --fault-ratio 0.1 --out data/generated/validation.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:  # numpy is an optional accelerator for the correlated sampler
    import numpy as np
    _HAVE_NUMPY = True
except ImportError:  # pragma: no cover - exercised only on a bare interpreter
    np = None  # type: ignore
    _HAVE_NUMPY = False

# ── column conventions (kept in sync with scripts/load_testbed.py) ──────────
FEATURE_FAMILIES: List[str] = [
    "min_Va_fault_pu",
    "max_Ia_fault",
    "max_I0_I1_fault",
    "max_I2_I1_fault",
    "mean_Vunb_fault",
    "recovery_Va_post",
]
METADATA_COLUMNS: List[str] = [
    "scenario_name", "fault_category", "fault_subtype", "fault_phases",
    "fault_branch_id", "fault_pos_pu", "fault_bus_id", "fault_location_km",
    "Zf_real_ohm", "Zf_imag_ohm",
]
TARGET_COLUMNS: List[str] = [
    "target_fault_type", "target_fault_category", "target_location_km",
]

# Voltage-like families sit near 1.0 and faults only push them DOWN, so "normal"
# is the HIGH tail. The rest are ~0 at rest and faults push them UP, so "normal"
# is the LOW tail.
VOLTAGE_FAMILIES = {"min_Va_fault_pu", "recovery_Va_post"}

# Sequence-ratio families: forced to ~0 at near-zero-current buses by the guard.
RATIO_FAMILIES = {"max_I0_I1_fault", "max_I2_I1_fault"}

# Physical clip bounds for generated normal values.
CLIP_BOUNDS = {
    "min_Va_fault_pu": (0.85, 1.05),
    "recovery_Va_post": (0.85, 1.05),
}  # spike families clip to >= 0 only


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _pct(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p / 100.0
    lo = int(math.floor(k))
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def detect_bus_ids(header: List[str]) -> List[str]:
    buses: List[str] = []
    for col in header:
        for fam in FEATURE_FAMILIES:
            pref = fam + "_"
            if col.startswith(pref):
                bus = col[len(pref):]
                if bus not in buses:
                    buses.append(bus)
    return buses


def feature_cols_for(bus_ids: List[str]) -> List[str]:
    """Canonical feature-column order (bus-major, family-minor).

    This SAME order is used by the envelope, the covariance, and the row writer,
    so the multivariate sample vector lines up with the columns it fills.
    """
    return [f"{fam}_{bus}" for bus in bus_ids for fam in FEATURE_FAMILIES]


def read_rows(path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames or [], list(reader) # type: ignore


def estimate_envelope(
    rows: List[Dict[str, str]],
    bus_ids: List[str],
    calm_pct: float = 30.0,
) -> Dict[str, Dict[str, Tuple[float, float]]]:
    """
    For each (bus, family) return (mean, std) of the CALM tail:
      - voltage families: values >= the (100-calm_pct) percentile  (high tail)
      - spike families:   values <= the calm_pct percentile        (low tail)
    """
    env: Dict[str, Dict[str, Tuple[float, float]]] = {}
    for bus in bus_ids:
        env[bus] = {}
        for fam in FEATURE_FAMILIES:
            col = f"{fam}_{bus}"
            vals = [_num(r.get(col)) for r in rows]
            vals = sorted(v for v in vals if math.isfinite(v))
            if not vals:
                env[bus][fam] = (0.0, 0.0)
                continue
            if fam in VOLTAGE_FAMILIES:
                thresh = _pct(vals, 100.0 - calm_pct)
                calm = [v for v in vals if v >= thresh]
            else:
                thresh = _pct(vals, calm_pct)
                calm = [v for v in vals if v <= thresh]
            if len(calm) < 2:
                calm = vals
            mean = statistics.fmean(calm)
            std = statistics.pstdev(calm) if len(calm) > 1 else 0.0
            std = max(std, abs(mean) * 0.01, 1e-6)  # small jitter floor
            env[bus][fam] = (mean, std)
    return env


def _clip(fam: str, value: float) -> float:
    lo, hi = CLIP_BOUNDS.get(fam, (0.0, None))
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def apply_lowcurrent_guard(env, bus_ids, min_current_frac: float) -> List[str]:
    """
    Sequence ratios (I0/I1, I2/I1) are ratios of currents; at a bus that normally
    carries almost no current the denominator ~ 0, so the ratio blows up to
    meaningless values. For such near-zero-current buses, force the normal ratio
    envelope to ~0. Returns the list of buses that were guarded.
    """
    currents = [env[b]["max_Ia_fault"][0] for b in bus_ids]
    max_c = max(currents) if currents else 0.0
    floor = max_c * min_current_frac
    guarded = []
    for b in bus_ids:
        if env[b]["max_Ia_fault"][0] < floor:
            env[b]["max_I0_I1_fault"] = (0.0, 0.005)
            env[b]["max_I2_I1_fault"] = (0.0, 0.005)
            guarded.append(b)
    return guarded


# ── correlated (multivariate) sampling 

def _family_of(col: str) -> Optional[str]:
    for fam in FEATURE_FAMILIES:
        if col.startswith(fam + "_"):
            return fam
    return None


def estimate_correlation(
    rows: List[Dict[str, str]],
    feat_cols: List[str],
    bus_ids: List[str],
    calm_rows_frac: float,
    shrinkage: float,
):
    """
    Estimate the inter-feature correlation matrix from the CALMEST rows.

    A fault always disturbs *some* bus, so no row is fully normal; but the least
    disturbed rows (smallest deepest-voltage-sag) are the closest thing to a
    near-normal operating snapshot, and their joint structure is what we want the
    generated normal to inherit. We compute Pearson correlation on that subset and
    shrink it toward the identity (denoise + guarantee positive-definiteness):
        R_shrunk = (1 - shrinkage) * R + shrinkage * I

    Returns (R_shrunk, n_calm) as a numpy array, or (None, 0) if numpy is absent /
    not enough finite rows.
    """
    if not _HAVE_NUMPY:
        return None, 0

    minva_cols = [f"min_Va_fault_pu_{b}" for b in bus_ids]
    mat = []
    sag = []
    for r in rows:
        vec = [_num(r.get(c)) for c in feat_cols]
        if not all(math.isfinite(v) for v in vec):
            continue
        mat.append(vec)
        # deepest sag over buses = strongest disturbance indicator for the row
        vsag = [_num(r.get(c)) for c in minva_cols]
        sag.append(1.0 - min(v for v in vsag if math.isfinite(v)))
    if len(mat) < len(feat_cols) + 2:
        return None, 0

    X = np.asarray(mat, dtype=float)
    sag = np.asarray(sag, dtype=float)
    k = max(len(feat_cols) + 2, int(round(len(X) * calm_rows_frac)))
    k = min(k, len(X))
    calm_idx = np.argsort(sag)[:k]
    Xc = X[calm_idx]

    R = np.corrcoef(Xc, rowvar=False)
    R = np.nan_to_num(R, nan=0.0)  # constant columns -> 0 correlation
    np.fill_diagonal(R, 1.0)
    R = (1.0 - shrinkage) * R + shrinkage * np.eye(len(feat_cols))
    return R, int(k)


def _build_cholesky(env, feat_cols, R, spread):
    """Compose Cov = D R D from the marginal stds and correlation, return (mean, L)."""
    means = []
    stds = []
    for col in feat_cols:
        fam = _family_of(col)
        bus = col[len(fam) + 1:]
        m, s = env[bus][fam]
        means.append(m)
        stds.append(max(s * spread, 1e-9))
    mean = np.asarray(means, dtype=float)
    s = np.asarray(stds, dtype=float)
    cov = (s[:, None] * s[None, :]) * R
    # jitter up the diagonal until Cholesky succeeds (PSD safety net)
    jitter = 0.0
    base = np.diag(cov).mean() * 1e-9 + 1e-12
    for _ in range(8):
        try:
            L = np.linalg.cholesky(cov + np.eye(len(cov)) * jitter)
            return mean, L
        except np.linalg.LinAlgError:
            jitter = base if jitter == 0.0 else jitter * 10
    # last resort: drop correlations, use diagonal covariance
    return mean, np.diag(s)


def generate_normal_rows_correlated(
    env, bus_ids, feat_cols, R, n: int, spread: float, seed: int
) -> List[Dict[str, str]]:
    rng = np.random.default_rng(seed)
    mean, L = _build_cholesky(env, feat_cols, R, spread)
    z = rng.standard_normal(size=(n, len(feat_cols)))
    samples = mean[None, :] + z @ L.T
    fams = [_family_of(c) for c in feat_cols]
    out = []
    for i in range(n):
        row = _meta_row(i)
        for j, col in enumerate(feat_cols):
            row[col] = f"{_clip(fams[j], float(samples[i, j])):.6g}"
        out.append(row)
    return out


def generate_normal_rows(env, bus_ids, n: int, rng: random.Random,
                         spread: float = 1.0) -> List[Dict[str, str]]:
    """v1 independent per-feature gauss sampler (numpy-free fallback)."""
    out = []
    for i in range(n):
        row = _meta_row(i)
        for bus in bus_ids:
            for fam in FEATURE_FAMILIES:
                mean, std = env[bus][fam]
                row[f"{fam}_{bus}"] = f"{_clip(fam, rng.gauss(mean, std * spread)):.6g}"
        out.append(row)
    return out


def _meta_row(i: int) -> Dict[str, str]:
    return {
        "scenario_name": f"NORMAL_{i:05d}",
        "fault_category": "NONE",
        "fault_subtype": "NONE",
        "fault_phases": "NONE",
        "fault_branch_id": "0",
        "fault_pos_pu": "0",
        "fault_bus_id": "0",
        "fault_location_km": "0",
        "Zf_real_ohm": "0",
        "Zf_imag_ohm": "0",
        "target_fault_type": "NO_FAULT",
        "target_fault_category": "NO_FAULT",
        "target_location_km": "0",
    }


def pick_fault_rows(rows, bus_ids, k: int, rng: random.Random) -> List[Dict[str, str]]:
    """Sample k real, finite fault rows from the source for injection."""
    feature_cols = feature_cols_for(bus_ids)

    def finite(r):
        return all(math.isfinite(_num(r.get(c))) for c in feature_cols)

    clean = [r for r in rows if finite(r)]
    if not clean or k <= 0:
        return []
    return (rng.sample(clean, k) if k <= len(clean)
            else [rng.choice(clean) for _ in range(k)])


def main():
    p = argparse.ArgumentParser(
        description="Generate NORMAL data (informed by the fault testbed) for the "
        "IsolationForest, optionally injecting real faults at a set ratio."
    )
    p.add_argument("--csv", required=True, help="Source fault testbed CSV")
    p.add_argument("--n-normal", type=int, default=4000, help="# normal rows to generate")
    p.add_argument("--fault-ratio", type=float, default=0.0,
                   help="Fraction of OUTPUT rows that should be real faults (0..0.9)")
    p.add_argument("--out", required=True, help="Output CSV path")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--min-current-frac", type=float, default=0.01,
                   help="Buses whose normal current is below this fraction of the "
                        "feeder's max normal current are treated as near-zero-current: "
                        "their sequence ratios (I0/I1, I2/I1) are forced to ~0.")
    p.add_argument("--spread", type=float, default=1.0,
                   help="Multiplier on the normal-envelope std. >1 widens the normal "
                        "(fewer false alarms, push toward mild faults); <1 tightens it.")
    p.add_argument("--calm-rows-frac", type=float, default=0.30,
                   help="Fraction of least-disturbed rows used to estimate the "
                        "correlation matrix for correlated sampling.")
    p.add_argument("--shrinkage", type=float, default=0.10,
                   help="Shrink the correlation matrix toward identity by this much "
                        "(denoise + keep it positive-definite). 0..1.")
    p.add_argument("--independent", action="store_true",
                   help="Force v1 independent per-feature sampling (no correlation).")
    args = p.parse_args()

    rng = random.Random(args.seed)
    header, rows = read_rows(args.csv)
    bus_ids = detect_bus_ids(header)
    feat_cols = feature_cols_for(bus_ids)
    print(f"[gen] source: {len(rows)} fault rows, buses={bus_ids}")

    env = estimate_envelope(rows, bus_ids)
    guarded = apply_lowcurrent_guard(env, bus_ids, args.min_current_frac)
    if guarded:
        print(f"[gen] low-current guard: forced sequence ratios ~0 for {guarded}")

    # Report the learned normal so it's auditable (voltage + current per bus).
    print("[gen] estimated normal envelope (mean per bus):")
    for bus in bus_ids:
        v = env[bus]["min_Va_fault_pu"][0]
        ia = env[bus]["max_Ia_fault"][0]
        i0 = env[bus]["max_I0_I1_fault"][0]
        print(f"       {bus}: min_Va~{v:.3f}  max_Ia~{ia:.3g}  I0/I1~{i0:.3g}")

    use_correlated = _HAVE_NUMPY and not args.independent
    R = None
    if use_correlated:
        R, n_calm = estimate_correlation(
            rows, feat_cols, bus_ids, args.calm_rows_frac, args.shrinkage
        )
        if R is None:
            use_correlated = False

    if use_correlated:
        # Decorrelate guarded ratio features so they sample independently near 0
        # rather than inheriting spurious coupling from the calm-row estimate.
        guarded_idx = [
            i for i, c in enumerate(feat_cols)
            if _family_of(c) in RATIO_FAMILIES and c[len(_family_of(c)) + 1:] in guarded
        ]
        for i in guarded_idx:
            R[i, :] = 0.0
            R[:, i] = 0.0
            R[i, i] = 1.0
        mean_abs = (abs(R) - np.eye(len(R))).sum() / (len(R) * (len(R) - 1))
        print(f"[gen] correlated sampling: R from {n_calm} calmest rows, "
              f"shrinkage={args.shrinkage}, mean|off-diag corr|={mean_abs:.3f}")
        normal = generate_normal_rows_correlated(
            env, bus_ids, feat_cols, R, args.n_normal, args.spread, args.seed
        )
    else:
        why = "forced --independent" if args.independent else "numpy unavailable"
        print(f"[gen] independent sampling ({why}); spread={args.spread}")
        normal = generate_normal_rows(env, bus_ids, args.n_normal, rng, args.spread)

    r = args.fault_ratio
    n_faults = round(args.n_normal * r / (1.0 - r)) if 0 < r < 1 else 0
    faults = pick_fault_rows(rows, bus_ids, n_faults, rng)

    combined = normal + faults
    rng.shuffle(combined)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(combined)

    total = len(combined)
    print(f"[gen] wrote {total} rows -> {out_path}")
    print(f"[gen]   normal: {len(normal)}  faults: {len(faults)}  "
          f"(fault fraction = {len(faults)/total:.1%})")


if __name__ == "__main__":
    main()
