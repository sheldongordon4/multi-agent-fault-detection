"""
reproduce_steps_1_4.py
======================
Run the first four paper reproduction steps as a single grouped workflow.

This retains the original behavior while making the purpose, order, and failure
handling easier to read and maintain.

Step 4 now optionally measures both local heuristic and LLM latency paths when
Azure credentials are configured in .env.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"

# Check if Azure is configured for LLM latency measurement
MEASURE_LLM_LATENCY = False
try:
    from app.faults.config import FaultsConfig
    faults_config = FaultsConfig()
    MEASURE_LLM_LATENCY = faults_config.azure_configured
except Exception:
    pass

STEPS = [
    ("reproduce_step1_generate_data", "Step 1 — Dataset generation"),
    ("reproduce_step2_detection", "Step 2 — Detection results  (Table 1, cross-feeder, escalation)"),
    ("reproduce_step3_classification", "Step 3 — Classification results  (Tables 2, 3, location)"),
    ("reproduce_step4_latency", "Step 4 — Pipeline latency  (Table 4)"),
]


def _run_step(module_name: str, description: str) -> bool:
    """Execute a reproduction step module and return whether it succeeded."""
    script_path = SCRIPT_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load step module: {module_name}")

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        module.main()
        return True
    except SystemExit as exc:
        print(f"\n[reproduce_steps_1_4] {description} exited with code {exc.code}", file=sys.stderr)
        return False
    except Exception as exc:  # pragma: no cover - diagnostic output path
        print(f"\n[reproduce_steps_1_4] {description} raised: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


def _measure_llm_latency() -> None:
    """
    Additional measurement: LLM path latency (only if Azure is configured).
    
    Loads the same 200 fault events used in step 4, measures run_fault_diagnosis()
    latency for each, and compares against the local heuristic path already
    measured in reproduce_step4_latency.py.
    """
    if not MEASURE_LLM_LATENCY:
        print("[reproduce_steps_1_4] Azure not configured; skipping LLM latency measurement.")
        return
    
    print("\n[reproduce_steps_1_4] Measuring LLM latency path (Azure configured)...")
    
    try:
        import numpy as np
        import pandas as pd
        from sklearn.ensemble import IsolationForest, RandomForestClassifier
        from app.faults.service import run_fault_diagnosis
        from scripts.load_testbed import feature_columns, load_testbed
        
        # Load data (same as step 4)
        bus13_csv = REPO_ROOT / "data" / "testbed" / "013 Bus Fault Analysis Batch (mod).csv"
        gen_dir = REPO_ROOT / "data" / "generated"
        train_013 = gen_dir / "normal_train_013.csv"
        n_events = 200
        
        if not bus13_csv.exists():
            print(f"[ERROR] Testbed not found: {bus13_csv}", file=sys.stderr)
            return
        
        # Load fault rows
        df = pd.read_csv(bus13_csv)
        fc = feature_columns(df)
        X = df[fc].apply(pd.to_numeric, errors="coerce")
        finite = np.isfinite(X.to_numpy()).all(axis=1)
        X_fault = X[finite].values[:n_events]
        df_fault = df[finite].reset_index(drop=True)[:n_events]
        
        # Load normal rows for IF training
        if train_013.exists():
            X_train, _, _ = load_testbed(train_013, target_col="target_fault_type")
            X_normal = X_train.values
        else:
            print("[step4_llm] WARNING: normal_train_013.csv not found.")
            X_normal = X_fault[:4000]
        
        # Train models (same as step 4)
        print("[step4_llm] Training models...")
        iforest = IsolationForest(n_estimators=200, contamination=0.01, random_state=42)
        iforest.fit(X_normal)
        
        y_type = df_fault["target_fault_type"].astype(str)
        rf_type = RandomForestClassifier(n_estimators=200, random_state=42)
        rf_type.fit(X_fault, y_type)
        
        buses = [c.split("_")[-1] for c in fc if c.startswith("min_Va_fault_pu_")]
        
        # Build detection payloads (same as step 4)
        print(f"[step4_llm] Building detection payloads for {n_events} events...")
        detections = []
        for i in range(n_events):
            row = X_fault[i].reshape(1, -1)
            pred = iforest.predict(row)[0]
            score = float(-iforest.decision_function(row)[0])
            severity = "low" if score < 0.05 else ("moderate" if score < 0.15 else "high")
            clf_out = None
            if pred == -1:
                ft = str(rf_type.predict(row)[0])
                clf_out = {"fault_type": ft, "location_km": None}
            
            top_bus = buses[0] if buses else "b_unknown"
            detection = {
                "isFault": pred == -1,
                "verdict": {"isFault": pred == -1, "anomalyScore": round(score, 4), "severity": severity},
                "classification": clf_out,
                "topBuses": [{"bus": top_bus}],
                "feeder": "ieee13",
            }
            detections.append(detection)
        
        # Measure LLM latency for diagnosed faults only
        print(f"[step4_llm] Timing run_fault_diagnosis() on detected faults...")
        times_llm = []
        diagnosed_count = 0
        
        for det in detections:
            if not det.get("isFault"):
                continue  # Only time diagnosed faults
            
            try:
                t0 = time.perf_counter()
                _ = run_fault_diagnosis(det)
                t1 = time.perf_counter()
                times_llm.append((t1 - t0) * 1000)
                diagnosed_count += 1
            except Exception as e:
                print(f"[step4_llm] WARNING: LLM call failed: {e}", file=sys.stderr)
                continue
        
        if not times_llm:
            print("[step4_llm] No diagnosed faults to measure; skipping LLM summary.", file=sys.stderr)
            return
        
        # Summarize
        llm_mean = float(np.mean(times_llm))
        llm_p95 = float(np.percentile(times_llm, 95))
        llm_p99 = float(np.percentile(times_llm, 99))
        
        print("\n" + "=" * 70)
        print("TABLE 4 EXTENSION — LLM path latency (measured)")
        print(f"          n={diagnosed_count} diagnosed faults (subset of {n_events})")
        print("=" * 70)
        print(f"{'Component':<50} {'Mean':>8} {'p95':>8}")
        print("-" * 70)
        print(f"{'LLM path (azure run_fault_diagnosis())':<50} "
              f"{llm_mean:>6.1f} ms {llm_p95:>6.1f} ms")
        print()
        print(f"Additional percentiles (LLM path):")
        print(f"  p99 = {llm_p99:.1f} ms")
        print(f"  Throughput = {1000 / llm_mean:.1f} events/sec (diagnosed only)")
        print()
        print("Note: LLM measurements require live Azure API access and .env config.")
        
    except ImportError as e:
        print(f"[step4_llm] Import error (likely app not on path): {e}", file=sys.stderr)
    except Exception as e:
        print(f"[step4_llm] Measurement failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()



def main() -> None:
    print("=" * 70)
    print("MAFD — Reproduction for Steps 1–4")
    print("=" * 70)
    print()

    overall_start = time.perf_counter()
    results: list[tuple[str, bool, float]] = []

    for module_name, description in STEPS:
        print(f"\n{'=' * 70}")
        print(f"  {description}")
        print(f"{'=' * 70}")
        start = time.perf_counter()
        success = _run_step(module_name, description)
        elapsed = time.perf_counter() - start
        results.append((description, success, elapsed))
        
        # After step 4, optionally measure LLM latency if Azure is configured
        if module_name == "reproduce_step4_latency" and success:
            _measure_llm_latency()

    total = time.perf_counter() - overall_start

    print("\n\n" + "=" * 70)
    print("REPRODUCTION SUMMARY")
    print("=" * 70)
    for desc, ok, elapsed in results:
        status = "OK" if ok else "FAILED"
        print(f"  [{status:^6}]  {desc:<52}  {elapsed:5.1f}s")
    print(f"\n  Total wall-clock time: {total:.1f}s")
    
    if MEASURE_LLM_LATENCY:
        print(f"  [INFO] LLM latency measurement enabled (Azure configured).")
    else:
        print(f"  [INFO] LLM latency measurement disabled (Azure not configured).")

    failed = [desc for desc, ok, _ in results if not ok]
    if failed:
        print(f"\n[WARNING] {len(failed)} step(s) failed:")
        for desc in failed:
            print(f"          {desc}")
        sys.exit(1)

    print("\n  All steps completed successfully.")


if __name__ == "__main__":
    main()
