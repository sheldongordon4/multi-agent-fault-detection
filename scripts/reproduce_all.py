"""
reproduce_all.py
=================
Master reproduction script for all empirical results in the MAFD paper.

    "MAFD: A Two-Layer Multi-Agent System for Electrical Grid Fault
     Detection and Diagnosis"

Runs all four reproduction steps in sequence:

    Step 1 — Dataset generation       (Section 4.2)
    Step 2 — Detection results        (Table 1, cross-feeder, escalation)
    Step 3 — Classification results   (Tables 2, 3, location regression)
    Step 4 — Pipeline latency         (Table 4)

Requirements
------------
    pip install scikit-learn xgboost numpy pandas

    The following testbed files must be present:
        data/testbed/013 Bus Fault Analysis Batch (mod).csv
        data/testbed/034 Bus Fault Analysis Batch (orig)/dataset_table.csv

    All generated datasets are written to data/generated/ by Step 1.

Reproducibility notes
---------------------
    All random seeds are fixed:
        Training data generation  : --seed 42
        Validation data generation: --seed 99
        Isolation Forest          : random_state=42, contamination=0.01
        Random Forest             : random_state=42, n_estimators=200
        XGBoost                   : random_state=42, n_estimators=200
        Cross-validation          : 5-fold stratified (sklearn default shuffle=False)

    Platform note: wall-clock latency measurements (Step 4, Table 4) are
    hardware-dependent. Reported paper values were measured on the development
    machine. Your values will differ by system; the relative ordering between
    components is reproducible.

Usage
-----
    python scripts/reproduce_all.py

    To run individual steps:
        python scripts/reproduce_step1_generate_data.py
        python scripts/reproduce_step2_detection.py
        python scripts/reproduce_step3_classification.py
        python scripts/reproduce_step4_latency.py
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parent.parent
SCRIPT_DIR  = REPO_ROOT / "scripts"

STEPS = [
    ("reproduce_step1_generate_data", "Step 1 — Dataset generation"),
    ("reproduce_step2_detection",     "Step 2 — Detection results  (Table 1, cross-feeder, escalation)"),
    ("reproduce_step3_classification","Step 3 — Classification results  (Tables 2, 3, location)"),
    ("reproduce_step4_latency",       "Step 4 — Pipeline latency  (Table 4)"),
]


def _run_step(module_name: str, description: str) -> bool:
    """Import and run a step module's main() function."""
    script_path = SCRIPT_DIR / f"{module_name}.py"
    spec   = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        module.main()
        return True
    except SystemExit as e:
        print(f"\n[reproduce_all] {description} exited with code {e.code}",
              file=sys.stderr)
        return False
    except Exception as exc:
        print(f"\n[reproduce_all] {description} raised: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


def main() -> None:
    print("=" * 70)
    print("MAFD — Full reproduction of all paper results")
    print("=" * 70)
    print()

    overall_start = time.perf_counter()
    results: list[tuple[str, bool, float]] = []

    for module_name, description in STEPS:
        print(f"\n{'=' * 70}")
        print(f"  {description}")
        print(f"{'=' * 70}")
        t0      = time.perf_counter()
        success = _run_step(module_name, description)
        elapsed = time.perf_counter() - t0
        results.append((description, success, elapsed))

    total = time.perf_counter() - overall_start

    print("\n\n" + "=" * 70)
    print("REPRODUCTION SUMMARY")
    print("=" * 70)
    for desc, ok, elapsed in results:
        status = "OK" if ok else "FAILED"
        print(f"  [{status:^6}]  {desc:<52}  {elapsed:5.1f}s")
    print(f"\n  Total wall-clock time: {total:.1f}s")

    failed = [d for d, ok, _ in results if not ok]
    if failed:
        print(f"\n[WARNING] {len(failed)} step(s) failed:")
        for d in failed:
            print(f"          {d}")
        sys.exit(1)
    else:
        print("\n  All steps completed successfully.")


if __name__ == "__main__":
    main()
