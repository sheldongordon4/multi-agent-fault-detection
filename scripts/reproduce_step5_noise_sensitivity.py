"""
reproduce_step5_noise_sensitivity.py
======================================
Reproduces Table 5 in the MAFD paper: Isolation Forest noise sensitivity
under Gaussian measurement noise and missing SCADA packet simulation.

Paper section:  4.5, 5.7, Table 5
Prerequisites:  reproduce_step1_generate_data.py must be run first.

Protocol (Section 4.5):
    - Isolation Forest trained once on clean synthetic normal data.
    - Validation feature matrix corrupted at increasing Gaussian noise levels.
    - Noise amplitude expressed as fraction of per-feature normal operating std.
      (This is the correct baseline — variation within the normal envelope,
       NOT variation across the full dataset including fault events.)
    - Separate missing-packet simulation zeros a random fraction of features,
      representing SCADA communication dropouts.
    - Random seed 42 for noise generation (reproducibility).

Model parameters:
    n_estimators=200, contamination=0.01, random_state=42

Usage:
    python scripts/reproduce_step5_noise_sensitivity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score

REPO_ROOT  = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from scripts.load_testbed import load_testbed  # noqa: E402

TRAIN_013 = REPO_ROOT / "data" / "generated" / "normal_train_013.csv"
VAL_013   = REPO_ROOT / "data" / "generated" / "validation_013.csv"

IF_PARAMS = dict(n_estimators=200, contamination=0.01, random_state=42)
NOISE_RNG_SEED = 42

# Gaussian noise levels as fraction of per-feature normal operating std
GAUSSIAN_LEVELS = [0.0, 0.05, 0.10, 0.20, 0.30, 0.50]

# Missing packet fractions (features zeroed at random)
MISSING_LEVELS = [0.05, 0.10, 0.20]


def _check_datasets() -> None:
    missing = [p for p in (TRAIN_013, VAL_013) if not p.exists()]
    if missing:
        print("[ERROR] Missing datasets. Run reproduce_step1_generate_data.py first.")
        for p in missing:
            print(f"        {p}")
        sys.exit(1)


def _metrics(is_fault: np.ndarray, flagged: np.ndarray,
             scores: np.ndarray) -> dict:
    tp = int((flagged & is_fault).sum())
    fp = int((flagged & ~is_fault).sum())
    fn = int((~flagged & is_fault).sum())
    tn = int((~flagged & ~is_fault).sum())
    prec  = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec   = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1    = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    far   = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    auprc = average_precision_score(is_fault.astype(int), scores)
    return dict(tp=tp, fp=fp, fn=fn, tn=tn,
                precision=prec, recall=rec, f1=f1, auprc=auprc, far=far)


def _evaluate_matrix(model: IsolationForest, X_test: np.ndarray, is_fault: np.ndarray) -> dict:
    flagged = model.predict(X_test) == -1
    scores = -model.decision_function(X_test)
    return _metrics(is_fault, flagged, scores)


def main() -> None:
    print("=" * 70)
    print("MAFD — Step 5: Noise sensitivity  (Table 5, Sections 4.5 and 5.7)")
    print("=" * 70)

    _check_datasets()

    print("\n[step5] Loading datasets...")
    X_train, _, _ = load_testbed(TRAIN_013, target_col="target_fault_type")
    X_val, y_val, _ = load_testbed(VAL_013, target_col="target_fault_type")
    is_fault = (y_val != "NO_FAULT").to_numpy()
    print(f"        Train: {len(X_train)} normal rows | Val: {len(X_val)} rows ({is_fault.sum()} faults)")

    print("[step5] Training Isolation Forest on clean normal data...")
    model = IsolationForest(**IF_PARAMS)
    model.fit(X_train.values)

    normal_std = X_train.values.std(axis=0)
    normal_std[normal_std == 0] = 1.0

    rng = np.random.default_rng(NOISE_RNG_SEED)

    print()
    print("=" * 75)
    print("TABLE 5 — Isolation Forest noise sensitivity (13-bus validation)")
    print("          Gaussian noise as fraction of per-feature normal-op std")
    print("=" * 75)
    hdr = (f"{'Condition':<22} {'Precision':>10} {'Recall':>8} "
           f"{'F1':>8} {'AUPRC':>8} {'FAR':>8} {'TP':>5} {'FP':>5} {'FN':>5}")
    print(hdr)
    print("-" * 75)

    for frac in GAUSSIAN_LEVELS:
        if frac == 0.0:
            X_test = X_val.values.copy()
            label = "Baseline (clean)"
        else:
            noise = rng.normal(0, frac * normal_std, size=X_val.shape)
            X_test = X_val.values + noise
            label = f"{frac * 100:.0f}% Gaussian noise"

        metrics = _evaluate_matrix(model, X_test, is_fault)
        print(f"{label:<22} {metrics['precision']:>10.4f} {metrics['recall']:>8.4f} "
              f"{metrics['f1']:>8.4f} {metrics['auprc']:>8.4f} {metrics['far']:>8.4f} "
              f"{metrics['tp']:>5} {metrics['fp']:>5} {metrics['fn']:>5}")

    print("-" * 75)

    for frac in MISSING_LEVELS:
        X_test = X_val.values.copy()
        mask = rng.random(X_val.shape) < frac
        X_test[mask] = 0.0
        label = f"{frac * 100:.0f}% missing packets"

        metrics = _evaluate_matrix(model, X_test, is_fault)
        print(f"{label:<22} {metrics['precision']:>10.4f} {metrics['recall']:>8.4f} "
              f"{metrics['f1']:>8.4f} {metrics['auprc']:>8.4f} {metrics['far']:>8.4f} "
              f"{metrics['tp']:>5} {metrics['fp']:>5} {metrics['fn']:>5}")

    print()
    print("Note: noise amplitude is relative to per-feature normal operating std,")
    print("      NOT the full dataset std (which includes large fault-event variation).")
    print("      The correct baseline reflects measurement noise within normal operation.")
    print("\n[step5] Done.")


if __name__ == "__main__":
    main()
