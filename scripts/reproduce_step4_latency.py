"""
reproduce_step4_latency.py
===========================
Reproduces the ML pipeline latency results reported in Table 4 of the MAFD paper.

Measures:
    - Isolation Forest scoring latency per fault event
    - Random Forest classification latency (conditional on IF flag)
    - Combined ML pipeline latency  (IF + RF, per event)
    - Local heuristic ticket generation latency
    - LLM path latency (via run_fault_diagnosis) — ONLY if Azure configured

Paper section: 5.4, Table 4
Note: LLM path latency is measured if Azure credentials are in .env.
      Otherwise, the estimated range of ~2,070 ms mean / ~5,070 ms p95 is retained.

Measurement protocol (Section 4.3):
    n_events = 200 fault event rows from the 13-bus labeled dataset
    Timer:   time.perf_counter() — wall-clock, per-event
    Both IF scoring and RF classification are included in each timed call.
    LLM measurements are optional (requires Azure credentials in .env).

Prerequisites:
    reproduce_step1_generate_data.py must be run first (not strictly needed
    for latency since we use the labeled dataset, but step 1 is part of the
    full reproduction chain).

Usage:
    python scripts/reproduce_step4_latency.py
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from scripts.load_testbed import feature_columns  # noqa: E402

# Check if Azure is configured for LLM latency measurement
MEASURE_LLM_LATENCY = False
try:
    from app.faults.config import FaultsConfig
    faults_config = FaultsConfig()
    MEASURE_LLM_LATENCY = faults_config.azure_configured
except Exception:
    pass

BUS13_CSV = REPO_ROOT / "data" / "testbed" / "013 Bus Fault Analysis Batch (mod).csv"

N_EVENTS = 200  # fault events to time (Section 4.3)
IF_PARAMS = dict(n_estimators=200, contamination=0.01, random_state=42)
RF_PARAMS = dict(n_estimators=200, random_state=42)
GEN_DIR = REPO_ROOT / "data" / "generated"
TRAIN_013 = GEN_DIR / "normal_train_013.csv"


@dataclass(frozen=True)
class LatencySummary:
    mean_ms: float
    p95_ms: float
    p99_ms: float


def _load_data() -> tuple[np.ndarray, pd.DataFrame, np.ndarray, list[str]]:
    """Load 13-bus fault rows and generated normal training rows."""
    df  = pd.read_csv(BUS13_CSV)
    fc  = feature_columns(df)
    X   = df[fc].apply(pd.to_numeric, errors="coerce")
    finite = np.isfinite(X.to_numpy()).all(axis=1)
    X_fault = X[finite].values
    df_fault = df[finite].reset_index(drop=True)

    if TRAIN_013.exists():
        from scripts.load_testbed import load_testbed
        X_train, _, _ = load_testbed(TRAIN_013, target_col="target_fault_type")
        X_normal = X_train.values
    else:
        print("[step4] WARNING: normal_train_013.csv not found — using fault rows as "
              "IF training proxy. Run step 1 for accurate results.")
        X_normal = X_fault[:4000]

    return X_fault[:N_EVENTS], df_fault[:N_EVENTS], X_normal, fc


def _build_local_ticket(detection: dict) -> dict:
    """Heuristic fallback ticket (replicates app/faults/service.py path)."""
    verdict    = detection.get("verdict", {})
    feeder     = detection.get("feeder", "unknown")
    severity   = verdict.get("severity", "medium")
    top_buses  = detection.get("topBuses", [{}])
    bus_id     = top_buses[0].get("bus", "unknown") if top_buses else "unknown"
    cls_out    = detection.get("classification") or {}
    ft         = cls_out.get("fault_type", "unknown")
    loc        = cls_out.get("location_km")
    fault_desc = f"{ft} near {bus_id}" + (f" (~{loc} km)" if loc is not None else "")
    return {
        "ticket_id":     f"LOCAL-{feeder}:{datetime.now(timezone.utc).isoformat()}",
        "feeder":        feeder,
        "fault_type":    fault_desc,
        "severity":      severity,
        "status":        "diagnosed",
        "root_cause":    "Inferred from per-bus symmetrical component signature.",
        "recommended_actions": [f"Inspect {bus_id} on feeder {feeder}."],
        "kb_citations":  [],
    }


def _summarize_latency(samples: list[float]) -> LatencySummary:
    return LatencySummary(
        mean_ms=float(np.mean(samples)),
        p95_ms=float(np.percentile(samples, 95)),
        p99_ms=float(np.percentile(samples, 99)),
    )


def _measure_llm_path(detections: list[dict]) -> LatencySummary | None:
    """
    Measure LLM path latency (run_fault_diagnosis).
    
    Only called if Azure is configured. Returns latency summary for diagnosed faults only.
    """
    if not MEASURE_LLM_LATENCY:
        return None
    
    print("[step4] Measuring LLM path latency...")
    try:
        from app.faults.service import run_fault_diagnosis
    except ImportError as e:
        print(f"[step4] WARNING: Could not import run_fault_diagnosis: {e}", file=sys.stderr)
        return None
    
    times_llm: list[float] = []
    diagnosed_count = 0
    
    for det in detections:
        if not det.get("isFault"):
            continue  # Only measure diagnosed faults
        
        try:
            t0 = time.perf_counter()
            _ = run_fault_diagnosis(det)
            t1 = time.perf_counter()
            times_llm.append((t1 - t0) * 1000)
            diagnosed_count += 1
        except Exception as e:
            print(f"[step4] WARNING: LLM call failed: {e}", file=sys.stderr)
            continue
    
    if not times_llm:
        print("[step4] No diagnosed faults; LLM latency measurement skipped.", file=sys.stderr)
        return None
    
    return _summarize_latency(times_llm)


def reproduce_table4() -> None:
    X_fault, df_fault, X_normal, fc = _load_data()

    buses = [c.split("_")[-1] for c in fc if c.startswith("min_Va_fault_pu_")]

    print(f"\n[step4] Training Isolation Forest (n_estimators=200)...")
    iforest = IsolationForest(**IF_PARAMS)
    iforest.fit(X_normal)

    print(f"[step4] Training Random Forest classifier (n_estimators=200)...")
    y_type = df_fault["target_fault_type"].astype(str)
    rf_type = RandomForestClassifier(**RF_PARAMS)
    rf_type.fit(X_fault, y_type)

    print(f"\n[step4] Timing ML pipeline on {N_EVENTS} fault events...")
    times_ml: list[float] = []
    times_heuristic: list[float] = []
    detections: list[dict] = []

    for i in range(N_EVENTS):
        row = X_fault[i].reshape(1, -1)

        t0 = time.perf_counter()
        pred = iforest.predict(row)[0]
        score = float(-iforest.decision_function(row)[0])
        severity = "low" if score < 0.05 else ("moderate" if score < 0.15 else "high")
        clf_out = None
        if pred == -1:
            ft = str(rf_type.predict(row)[0])
            clf_out = {"fault_type": ft, "location_km": None}
        t1 = time.perf_counter()
        times_ml.append((t1 - t0) * 1000)

        top_bus = buses[0] if buses else "b_unknown"
        detection = {
            "isFault": pred == -1,
            "verdict": {"isFault": pred == -1, "anomalyScore": round(score, 4), "severity": severity},
            "classification": clf_out,
            "topBuses": [{"bus": top_bus}],
            "feeder": "ieee13",
        }
        detections.append(detection)

    print(f"[step4] Timing local heuristic ticket generation...")
    for det in detections:
        t0 = time.perf_counter()
        _build_local_ticket(det)
        t1 = time.perf_counter()
        times_heuristic.append((t1 - t0) * 1000)

    ml_summary = _summarize_latency(times_ml)
    heuristic_summary = _summarize_latency(times_heuristic)
    end_to_end = [a + b for a, b in zip(times_ml, times_heuristic)]
    e2e_summary = _summarize_latency(end_to_end)
    
    # Optionally measure LLM path
    llm_summary = _measure_llm_path(detections)

    print("\n" + "=" * 75)
    print("TABLE 4 — MAFD pipeline latency")
    print(f"          n={N_EVENTS} fault events, 13-bus, local hardware")
    print("=" * 75)
    print(f"{'Component':<50} {'Mean':>10} {'p95':>10}")
    print("-" * 75)
    print(f"{'ML detection layer (IF + RF classification)':<50} "
          f"{ml_summary.mean_ms:>8.1f} ms {ml_summary.p95_ms:>8.1f} ms")
    print(f"{'Local heuristic ticket generation':<50} "
          f"{heuristic_summary.mean_ms:>7.3f} ms {heuristic_summary.p95_ms:>7.3f} ms")
    print(f"{'End-to-end, local heuristic path':<50} "
          f"{e2e_summary.mean_ms:>8.1f} ms {e2e_summary.p95_ms:>8.1f} ms")
    
    if llm_summary:
        # Count diagnosed faults
        diagnosed = sum(1 for d in detections if d.get("isFault"))
        print(f"{'End-to-end, LLM path (measured, n=' + str(diagnosed) + ')':<50} "
              f"{llm_summary.mean_ms:>8.1f} ms {llm_summary.p95_ms:>8.1f} ms")
    else:
        print(f"{'End-to-end, LLM path (estimated)':<50} "
              f"{'~2,070 ms':>10} {'~5,070 ms':>10}")
    
    print()
    print(f"Additional percentiles (ML pipeline):")
    print(f"  p99 = {ml_summary.p99_ms:.1f} ms")
    print(f"  Throughput = {1000 / ml_summary.mean_ms:.0f} events/sec")
    
    if llm_summary:
        print(f"\nAdditional percentiles (LLM path):")
        print(f"  p99 = {llm_summary.p99_ms:.1f} ms")
        diagnosed = sum(1 for d in detections if d.get("isFault"))
        print(f"  Throughput = {1000 / llm_summary.mean_ms:.1f} events/sec (diagnosed only, n={diagnosed})")
    else:
        print("\nNote: LLM latency is an unmeasured Azure OpenAI structured-JSON estimate.")


def main() -> None:
    if not BUS13_CSV.exists():
        print(f"[ERROR] Testbed not found: {BUS13_CSV}", file=sys.stderr)
        sys.exit(1)
    print("=" * 75)
    print("MAFD — Step 4: Pipeline latency  (Table 4)")
    print("=" * 75)
    
    if MEASURE_LLM_LATENCY:
        print("[INFO] Azure is configured; LLM latency will be measured.")
    else:
        print("[INFO] Azure not configured; LLM latency will be estimated.")
    
    reproduce_table4()
    print("\n[step4] Done.")


if __name__ == "__main__":
    main()
