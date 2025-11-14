from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

# Optional: try to use FastAPI backend if available
try:
    import requests  # type: ignore[import-untyped]
except Exception:  # noqa: BLE001
    requests = None  # type: ignore[assignment]


# Default to the same directory used in the Makefile / scripts
INCIDENTS_DIR = Path(os.getenv("INCIDENTS_DIR", "artifacts/incidents"))

# Optional local signals CSV for hybrid mode
SIGNALS_CSV_PATH = Path("artifacts/signals/demo_signals.csv")


@dataclass
class FaultTicket:
    ticket_id: str
    scenario: Optional[str]
    bus_id: Optional[str]
    fault_type: Optional[str]
    severity: Optional[str]
    status: Optional[str]
    summary: Optional[str]
    root_cause: Optional[str]
    recommended_actions: List[str]
    evidence: List[Dict[str, Any]]
    kb_citations: List[Dict[str, Any]]
    raw: Dict[str, Any]
    source_file: Path
    mtime: float

    @classmethod
    def from_json(cls, path: Path) -> "FaultTicket":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        ticket_id = data.get("ticket_id") or data.get("id") or path.stem
        scenario = data.get("scenario")
        bus_id = data.get("bus_id") or data.get("busId")
        fault_type = data.get("fault_type") or data.get("faultType")
        severity = data.get("severity")
        status = data.get("status")

        summary_obj = data.get("summary")
        if isinstance(summary_obj, dict):
            summary = summary_obj.get("text") or json.dumps(summary_obj)
        else:
            summary = summary_obj

        root_cause = data.get("root_cause") or data.get("rootCause")

        recommended_actions = (
            data.get("recommended_actions")
            or data.get("recommendedActions")
            or []
        )
        if not isinstance(recommended_actions, list):
            recommended_actions = [str(recommended_actions)]

        evidence = data.get("evidence") or []
        if not isinstance(evidence, list):
            evidence = [evidence]

        kb_citations = data.get("kb_citations") or data.get("kbCitations") or []
        if not isinstance(kb_citations, list):
            kb_citations = [kb_citations]

        stat = path.stat()

        return cls(
            ticket_id=str(ticket_id),
            scenario=scenario,
            bus_id=bus_id,
            fault_type=fault_type,
            severity=severity,
            status=status,
            summary=summary,
            root_cause=root_cause,
            recommended_actions=recommended_actions,
            evidence=evidence,
            kb_citations=kb_citations,
            raw=data,
            source_file=path,
            mtime=stat.st_mtime,
        )


# ---------- Helpers: severity, summary stats, signals, etc. ----------


def format_severity_tag(severity: Optional[str]) -> str:
    s = (severity or "unknown").lower()
    mapping = {
        "info": "🔵 info",
        "low": "🟢 low",
        "medium": "🟡 medium",
        "high": "🔴 high",
        "unknown": "⚪ unknown",
    }
    return mapping.get(s, mapping["unknown"])


def get_summary_stats(ticket: FaultTicket) -> Dict[str, Any]:
    """
    Extract structured summary stats from the raw ticket JSON, if present.
    """
    summary_raw = ticket.raw.get("summary") or {}
    if not isinstance(summary_raw, dict):
        return {}

    stats = {
        "nPoints": summary_raw.get("nPoints"),
        "nAnomalies": summary_raw.get("nAnomalies"),
        "meanAnomalyScore": summary_raw.get("meanAnomalyScore"),
    }
    return stats


def load_tickets(incidents_dir: Path) -> List[FaultTicket]:
    tickets: List[FaultTicket] = []

    if not incidents_dir.exists():
        return tickets

    for path in sorted(incidents_dir.glob("**/*.json")):
        try:
            ticket = FaultTicket.from_json(path)
            tickets.append(ticket)
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Could not load ticket from {path}: {exc}")

    tickets.sort(key=lambda t: t.mtime, reverse=True)
    return tickets


def ticket_list_dataframe(tickets: List[FaultTicket]) -> pd.DataFrame:
    rows = []
    for idx, t in enumerate(tickets):
        rows.append(
            {
                "index": idx,
                "Ticket ID": t.ticket_id,
                "Scenario": t.scenario,
                "Bus": t.bus_id,
                "Fault Type": t.fault_type,
                "Severity": format_severity_tag(t.severity),
                "Status": t.status,
                "Source": t.source_file.name,
            }
        )
    df = pd.DataFrame(rows)
    df.set_index("index", inplace=True)
    return df


# ---------- Hybrid signal fetcher: CSV → FastAPI → synthetic ----------


def _try_signal_from_csv(
    metric: str, start_ts: Optional[str], end_ts: Optional[str]
) -> Optional[pd.DataFrame]:
    if not SIGNALS_CSV_PATH.exists():
        return None

    try:
        df = pd.read_csv(SIGNALS_CSV_PATH)
    except Exception:  # noqa: BLE001
        return None

    if "timestamp" not in df.columns:
        return None

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

    # Optional metric column filtering if present
    if "metric" in df.columns:
        df = df[df["metric"] == metric]

    if start_ts:
        start_dt = pd.to_datetime(start_ts, utc=True, errors="coerce")
        df = df[df["timestamp"] >= start_dt]
    if end_ts:
        end_dt = pd.to_datetime(end_ts, utc=True, errors="coerce")
        df = df[df["timestamp"] <= end_dt]

    if df.empty:
        return None

    # Normalize to [timestamp, value] where possible
    value_col = None
    for col in df.columns:
        if col in ("timestamp", "metric", "bus_id", "scenario"):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            value_col = col
            break

    if value_col is None:
        return None

    return df[["timestamp", value_col]].rename(columns={value_col: "value"})


def _try_signal_from_api(
    metric: str,
    start_ts: Optional[str],
    end_ts: Optional[str],
    bus_id: Optional[str],
    scenario: Optional[str],
) -> Optional[pd.DataFrame]:
    if requests is None:
        return None

    base_url = os.getenv("SIGNALS_API_URL", "http://localhost:8000/signals/window")

    params: Dict[str, Any] = {"metric": metric}
    if start_ts:
        params["start"] = start_ts
    if end_ts:
        params["end"] = end_ts
    if bus_id:
        params["bus_id"] = bus_id
    if scenario:
        params["scenario"] = scenario

    try:
        resp = requests.get(base_url, params=params, timeout=2.0)
        if not resp.ok:
            return None
        data = resp.json()
        df = pd.DataFrame(data)
    except Exception:  # noqa: BLE001
        return None

    if "timestamp" not in df.columns:
        return None

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

    value_col = None
    for col in df.columns:
        if col in ("timestamp", "metric", "bus_id", "scenario"):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            value_col = col
            break

    if value_col is None:
        return None

    return df[["timestamp", value_col]].rename(columns={value_col: "value"})


def _synthetic_signal_window(
    metric: str,
    start_ts: Optional[str],
    end_ts: Optional[str],
) -> pd.DataFrame:
    """
    Fallback: generate a synthetic signal window so the dean sees a plot
    even if there is no real backend yet.
    """
    n = 200
    if start_ts:
        start_dt = pd.to_datetime(start_ts, utc=True, errors="coerce")
    else:
        start_dt = pd.Timestamp.utcnow()
    if end_ts:
        end_dt = pd.to_datetime(end_ts, utc=True, errors="coerce")
    else:
        end_dt = start_dt + pd.Timedelta(seconds=n)

    # Uniform spacing between start and end
    timestamps = pd.date_range(start=start_dt, end=end_dt, periods=n)

    # Simple oscillatory synthetic signal
    t = np.linspace(0, 4 * np.pi, n)
    base = np.sin(t)  # core waveform
    noise = 0.1 * np.random.randn(n)
    value = base + noise

    return pd.DataFrame({"timestamp": timestamps, "value": value})


def get_signal_window(
    metric: str,
    start_ts: Optional[str],
    end_ts: Optional[str],
    bus_id: Optional[str],
    scenario: Optional[str],
) -> pd.DataFrame:
    """
    Hybrid strategy:
    1) Try local CSV: artifacts/signals/demo_signals.csv
    2) Try FastAPI endpoint: GET /signals/window
    3) Fall back to synthetic signal (demo mode)
    """
    # 1) CSV
    df = _try_signal_from_csv(metric, start_ts, end_ts)
    if df is not None and not df.empty:
        df["source"] = "csv"
        return df

    # 2) FastAPI
    df = _try_signal_from_api(metric, start_ts, end_ts, bus_id, scenario)
    if df is not None and not df.empty:
        df["source"] = "api"
        return df

    # 3) Synthetic fallback
    df = _synthetic_signal_window(metric, start_ts, end_ts)
    df["source"] = "synthetic"
    return df


# ---------- Render helpers ----------


def render_ticket_header(ticket: FaultTicket) -> None:
    left, right = st.columns([0.7, 0.3])

    with left:
        st.subheader(f"Ticket: {ticket.ticket_id}")
        line_bits = []
        if ticket.scenario:
            line_bits.append(f"Scenario: **{ticket.scenario}**")
        if ticket.bus_id:
            line_bits.append(f"Bus: **{ticket.bus_id}**")
        if ticket.fault_type:
            line_bits.append(f"Type: **{ticket.fault_type}**")
        st.markdown(" · ".join(line_bits))

    with right:
        sev_tag = format_severity_tag(ticket.severity)
        status = ticket.status or "unknown"
        st.markdown(f"**Severity:** {sev_tag}")
        st.markdown(f"**Status:** `{status}`")
        st.caption(f"Source file: `{ticket.source_file}`")


def render_reasoning(ticket: FaultTicket) -> None:
    st.markdown("### Reasoning summary")

    if ticket.summary:
        st.markdown("**Summary**")
        st.write(ticket.summary)

    if ticket.root_cause:
        st.markdown("**Root cause**")
        st.write(ticket.root_cause)

    if ticket.recommended_actions:
        st.markdown("**Recommended actions**")
        for i, action in enumerate(ticket.recommended_actions, start=1):
            st.markdown(f"{i}. {action}")


def render_evidence(ticket: FaultTicket) -> None:
    st.markdown("### Evidence & flagged signals")

    if not ticket.evidence:
        st.info("No evidence attached to this ticket.")
        return

    # Evidence table
    ev_rows = []
    for ev in ticket.evidence:
        ev_rows.append(
            {
                "Metric": ev.get("metric"),
                "Start": ev.get("start_timestamp"),
                "End": ev.get("end_timestamp"),
                "Description": ev.get("description"),
            }
        )

    df = pd.DataFrame(ev_rows)
    st.dataframe(df, use_container_width=True)

    # Try to plot the first evidence window that has a metric
    first_ev = next((ev for ev in ticket.evidence if ev.get("metric")), None)

    if first_ev is None:
        st.info("Evidence has no metric field; showing table only.")
        return

    metric = first_ev.get("metric")
    start_ts = first_ev.get("start_timestamp")
    end_ts = first_ev.get("end_timestamp")

    df_sig = get_signal_window(metric, start_ts, end_ts, ticket.bus_id, ticket.scenario)

    if df_sig is None or df_sig.empty:
        st.info("No signal data available for this evidence window.")
        return

    source = df_sig.get("source", pd.Series(["unknown"])).iloc[0]

    st.markdown("#### Flagged signal window")
    st.caption(
        f"Signal source: **{source}** "
        "(csv/api/synthetic). In production, this will be wired to SCADA "
        "or your timeseries backend."
    )

    # Plot using timestamp as index
    plot_df = df_sig.set_index("timestamp")[["value"]]
    st.line_chart(plot_df, use_container_width=True)


def render_kb_citations(ticket: FaultTicket) -> None:
    st.markdown("### Knowledge base citations")

    if not ticket.kb_citations:
        st.info("No KB citations attached to this ticket.")
        return

    rows = []
    for c in ticket.kb_citations:
        rows.append(
            {
                "Source ID": c.get("source_id") or c.get("id"),
                "Title": c.get("title"),
                "Section": c.get("section"),
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)


def render_raw_json(ticket: FaultTicket) -> None:
    with st.expander("Raw ticket JSON", expanded=False):
        st.json(ticket.raw)


def render_ai_reasoning(ticket: FaultTicket) -> None:
    st.markdown("### AI reasoning (demo mode)")

    stats = get_summary_stats(ticket)
    n_points = stats.get("nPoints")
    n_anom = stats.get("nAnomalies")
    mean_score = stats.get("meanAnomalyScore")

    severity = (ticket.severity or "unknown").lower()
    scenario = ticket.scenario or "unknown_scenario"
    bus_id = ticket.bus_id or "unknown_bus"

    # Short narrative tuned for your MVP story
    reasoning = []

    reasoning.append(
        f"For scenario **'{scenario}'** on **{bus_id}**, the detector analyzed "
        f"**{n_points}** points and found **{n_anom}** anomaly windows "
        f"with a mean anomaly score of **{mean_score}**."
    )

    if severity == "high":
        reasoning.append(
            "The anomaly rate and pattern are consistent with a **high-severity** "
            "event. Operators should treat this as a priority incident and confirm "
            "whether loading, protection settings, or recent switching actions "
            "could explain the behavior."
        )
    elif severity == "medium":
        reasoning.append(
            "The anomaly pattern suggests a **medium-severity** condition. It may "
            "reflect emerging stress on the feeder or asset, and it is worth "
            "reviewing trends and recent operational changes."
        )
    elif severity == "low":
        reasoning.append(
            "The anomaly rate is elevated but still within a **low-severity** band. "
            "This is suitable for monitoring and trend analysis rather than "
            "immediate intervention, unless corroborating alarms exist."
        )
    elif severity == "info":
        reasoning.append(
            "The detector did not identify a significant anomaly cluster. This "
            "ticket is informational and can be used to validate the detection "
            "pipeline rather than to drive operational action."
        )
    else:
        reasoning.append(
            "Severity is currently classified as **unknown** based on the available "
            "summary statistics. In a full deployment, additional context from "
            "SCADA and historical behavior would refine this assessment."
        )

    reasoning.append(
        "This explanation is generated in **demo mode** using the ticket metadata "
        "only. In the full Coherence Engine, a dedicated reasoning layer (LLM or "
        "expert rules) would incorporate detailed waveforms, protection logs, and "
        "system topology to produce richer, operator-ready narratives."
    )

    for paragraph in reasoning:
        st.write(paragraph)


# ---------- Main app ----------


def main() -> None:
    st.set_page_config(
        page_title="MAFD – Fault Browser",
        page_icon="⚡",
        layout="wide",
    )

    st.title("⚡ Multi-Agent Fault Detection – Fault Browser")
    st.caption(
        "Streamlit UI for browsing fault tickets, flagged signals, and reasoning "
        "summaries (Goal 4 – Streamlit UI and Demo Preparation)."
    )

    tickets = load_tickets(INCIDENTS_DIR)

    # Light debug / context info
    st.caption(
        f"Incidents directory: `{INCIDENTS_DIR}` · "
        f"Tickets loaded: **{len(tickets)}**"
    )

    st.sidebar.header("Controls")
    st.sidebar.markdown(f"**Incidents dir**: `{INCIDENTS_DIR}`")
    refresh_clicked = st.sidebar.button("🔄 Refresh tickets")
    if refresh_clicked:
        st.experimental_rerun()

    if not tickets:
        st.info(
            "No tickets found.\n\n"
            "Run `make ticket-demo` from the project root to generate a demo ticket, "
            "then refresh this page."
        )
        return

    scenarios = sorted({t.scenario for t in tickets if t.scenario})
    severities = sorted({t.severity for t in tickets if t.severity})

    selected_scenario = st.sidebar.multiselect(
        "Filter by scenario", options=scenarios, default=scenarios
    )
    selected_severity = st.sidebar.multiselect(
        "Filter by severity", options=severities, default=severities
    )

    filtered = [
        t
        for t in tickets
        if (not selected_scenario or t.scenario in selected_scenario)
        and (not selected_severity or t.severity in selected_severity)
    ]

    if not filtered:
        st.info("No tickets match the current filters.")
        return

    df_list = ticket_list_dataframe(filtered)

    list_col, detail_col = st.columns([0.45, 0.55])

    with list_col:
        st.subheader("Tickets")
        st.dataframe(df_list, use_container_width=True, height=400)

        selected_index = st.selectbox(
            "Select ticket",
            options=list(df_list.index),
            format_func=lambda idx: f"{df_list.loc[idx, 'Ticket ID']} "
            f"({df_list.loc[idx, 'Scenario'] or 'no-scenario'})",
        )

        selected_ticket = filtered[selected_index]

    with detail_col:
        render_ticket_header(selected_ticket)
        st.markdown("---")
        render_reasoning(selected_ticket)
        st.markdown("---")
        render_evidence(selected_ticket)
        st.markdown("---")
        render_kb_citations(selected_ticket)
        st.markdown("---")
        render_ai_reasoning(selected_ticket)
        st.markdown("---")
        render_raw_json(selected_ticket)


if __name__ == "__main__":
    main()
