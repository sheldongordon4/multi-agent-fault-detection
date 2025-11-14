#!/usr/bin/env python
"""
make_ticket_from_demo.py

Small CLI helper for Goal 4.

Usage (typical):
    python scripts/run_detection_demo.py --scenario overload_trip --bus_id bus_1 \
        | python scripts/make_ticket_from_demo.py

It:
- Reads JSON from stdin (or --input file)
- Expects keys: scenario, busId/bus_id, summary.{nPoints, nAnomalies, meanAnomalyScore}
- Writes a ticket JSON into artifacts/incidents/
- Ticket is compatible with the Streamlit Fault Browser UI and is clearly labeled
  as a local/demo ticket (no external LLM).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


DEFAULT_INCIDENTS_DIR = Path("artifacts/incidents")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert detection demo summary JSON into a fault ticket."
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to input JSON file. If omitted, reads from stdin.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_INCIDENTS_DIR),
        help=f"Directory to write ticket JSON (default: {DEFAULT_INCIDENTS_DIR})",
    )
    return parser.parse_args()


def load_summary(args: argparse.Namespace) -> Dict[str, Any]:
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        data = sys.stdin.read()
        if not data.strip():
            raise SystemExit(
                "No input provided. Pipe JSON from run_detection_demo.py or use --input."
            )
        return json.loads(data)


def infer_severity(summary: Dict[str, Any]) -> str:
    """
    Simple, explainable severity heuristic for demo tickets.

    Uses anomaly *rate* when possible so it behaves reasonably as nPoints changes.
    """
    n_points = summary.get("nPoints")
    n_anom = summary.get("nAnomalies")

    try:
        n_points = int(n_points) if n_points is not None else None
    except Exception:  # noqa: BLE001
        n_points = None

    try:
        n_anom = int(n_anom) if n_anom is not None else None
    except Exception:  # noqa: BLE001
        n_anom = None

    if n_anom is None or n_points in (None, 0):
        return "unknown"

    if n_anom == 0:
        return "info"

    # anomaly rate per point
    rate = n_anom / max(n_points, 1)

    # Tunable but simple buckets:
    # - very low anomaly rate: low
    # - moderate: medium
    # - higher: high
    if rate < 0.01:
        return "low"
    if rate < 0.05:
        return "medium"
    return "high"


def build_ticket(payload: Dict[str, Any]) -> Dict[str, Any]:
    scenario = payload.get("scenario") or "unknown_scenario"
    bus_id = payload.get("bus_id") or payload.get("busId") or "unknown_bus"
    summary = payload.get("summary") or {}

    n_points = summary.get("nPoints")
    n_anomalies = summary.get("nAnomalies")
    mean_score = summary.get("meanAnomalyScore")

    # NEW: signal window metadata from run_detection_demo.py
    signal_window_start = payload.get("signalWindowStart")
    signal_window_end = payload.get("signalWindowEnd")
    signal_metric = payload.get("signalMetric", "current")

    ticket_id = f"LOCAL-{scenario}-{bus_id}"

    fault_type = f"{scenario.replace('_', ' ').title()} on {bus_id}"
    severity = infer_severity(summary)
    status = "diagnosed"

    # Timestamp for traceability
    now = datetime.now(timezone.utc).isoformat()

    # Human-facing summary text, explicitly framed as a local demo ticket
    summary_text = (
        f"This is a local demo ticket for scenario '{scenario}' on {bus_id}. "
        f"The anomaly detector analyzed {n_points} points, found {n_anomalies} "
        f"anomaly windows, and produced a mean anomaly score of {mean_score}. "
        f"Based on this run, the ticket severity is classified as **{severity}**. "
        "No external LLM was called; this ticket was generated purely from the "
        "local detector summary to exercise the end-to-end MVP pipeline "
        "(detector → ticket → Streamlit UI)."
    )

    ticket = {
        "ticket_id": ticket_id,
        "scenario": scenario,
        "bus_id": bus_id,
        "fault_type": fault_type,
        "severity": severity,
        "status": status,
        "created_at": now,
        "summary": {
            "text": summary_text,
            "nPoints": n_points,
            "nAnomalies": n_anomalies,
            "meanAnomalyScore": mean_score,
            "raw": summary,  # keep original summary blob for debugging
        },
        "root_cause": (
            "Potential fault condition inferred from the demo scenario label and "
            "detector output. In a production deployment, this narrative would be "
            "refined by your reasoning layer (LLM or expert rules) using the "
            "underlying SCADA signals and protection context."
        ),
        "recommended_actions": [
            "Review the affected feeder or asset around the indicated analysis window.",
            "Check for recent operational or load changes that could explain the anomalies.",
            "Cross-check detector output against SCADA waveforms and protection logs.",
        ],
        "evidence": [
            {
                "metric": signal_metric,
                "start_timestamp": signal_window_start,
                "end_timestamp": signal_window_end,
                "description": (
                    "Signal window used by the demo detector run. "
                    "These timestamps align with the values stored in "
                    "artifacts/signals/demo_signals.csv for visualization "
                    "in the Streamlit UI."
                ),
            }
        ],
        "kb_citations": [],
        "meta": {
            "source": "run_detection_demo.py",
            "build_helper": "make_ticket_from_demo.py",
            "mode": "local_demo",
            "pipeline": "detector→ticket→ui",
        },
    }


    return ticket


def main() -> None:
    args = parse_args()
    payload = load_summary(args)
    ticket = build_ticket(payload)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"{ticket['ticket_id']}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(ticket, f, indent=2)

    print(f"Wrote ticket to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
