import json
import logging
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.faults import budget
from app.faults.budget import LLMBudgetExceeded
from app.faults.config import settings as faults_settings
from app.faults.constants import SYSTEM_PROMPT
from app.faults.schemas import FaultTicket
from app.rag.retriever import kb_retrieve_impl  # direct KB retrieval for local mode

logger = logging.getLogger(__name__)

# Fall back to the offline heuristic ticket only when Azure is not configured
# (not on APP_ENV), so a configured endpoint works even with APP_ENV=local in dev.
USE_LOCAL_FALLBACK = not faults_settings.azure_configured


def _should_use_local() -> bool:
    """
    Use the local (no-LLM) fallback when Azure isn't configured OR the process
    endpoint-call budget is spent. The budget check makes the switch permanent
    once we hit the cap, so no further Azure calls are attempted.
    """
    return USE_LOCAL_FALLBACK or budget.exhausted()


# -------------------------------------------------------------------
# Detection-event helpers
# -------------------------------------------------------------------


def _read_detection(detection: dict[str, Any]) -> tuple[str, str, Any, list[dict[str, Any]], str]:
    """
    Normalize an anomalies.detected payload (or a manual API body) into
    (feeder, severity, anomaly_score, top_buses, incident_id).
    """
    verdict = detection.get("verdict", {}) or {}
    feeder = detection.get("feeder") or "unknown_feeder"
    severity = verdict.get("severity") or detection.get("severity") or "medium"
    score = verdict.get("anomalyScore", detection.get("anomaly_score"))
    top_buses = detection.get("topBuses") or detection.get("top_buses") or []
    incident_id = (
        detection.get("incident_id")
        or detection.get("eventId")
        or f"{feeder}:{detection.get('timestamp')}"
    )
    return feeder, severity, score, top_buses, incident_id


def _detection_summary(
    feeder: str, severity: str, score: Any, top_buses: list[dict[str, Any]]
) -> str:
    lines = [
        f"Feeder: {feeder}",
        f"Detector severity: {severity}",
        f"Anomaly score: {score}",
        "Most-disturbed buses (per-bus fault signature):",
    ]
    for b in top_buses:
        lines.append(
            f"- {b.get('bus')}: minVa={b.get('minVa')}, maxIa={b.get('maxIa')}, "
            f"max_I0_I1={b.get('maxI0I1')}, max_I2_I1={b.get('maxI2I1')}"
        )
    return "\n".join(lines)


# Lazily-built agent graph (LLM + kb_retrieve + ReAct loop). Only constructed in
# non-local mode, so importing this module never requires Azure credentials.
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        from app.faults.agent import build_coordinator_graph

        _graph = build_coordinator_graph()
    return _graph


def _coerce_to_ticket(raw: Any) -> dict[str, Any]:
    """
    Turn the LLM's final message into a validated FaultTicket dict.

    Accepts a dict or a string (possibly wrapped in prose), extracts the JSON
    object, and best-effort validates it against the FaultTicket schema without
    crashing the request if a field is slightly off.
    """
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"LLM did not return a JSON object: {text[:200]}")
        data = json.loads(text[start : end + 1])

    try:
        FaultTicket(**data)  # validate; raises if the schema is wrong
    except Exception as exc:  # noqa: BLE001
        data.setdefault("_validation_warning", str(exc))

    return data


# -------------------------------------------------------------------
# Local/offline fallback (no LLM calls)
# -------------------------------------------------------------------


def _build_local_fault_ticket(detection: dict[str, Any]) -> dict[str, Any]:
    """
    Local fallback: build a plausible FaultTicket from the detection event using
    simple signature heuristics + direct KB retrieval, without calling any LLM.
    """
    feeder, severity, score, top_buses, incident_id = _read_detection(detection)
    top = top_buses[0] if top_buses else {}
    bus_id = top.get("bus", "unknown_bus")

    i0i1 = top.get("maxI0I1") or 0.0
    i2i1 = top.get("maxI2I1") or 0.0
    min_va = top.get("minVa")

    # Prefer the supervised classifier's label when detection attached one;
    # otherwise fall back to the cheap signature heuristic.
    classification = detection.get("classification") or {}
    if classification.get("fault_type"):
        loc = classification.get("location_km")
        fault_type = f"{classification['fault_type']} near {bus_id}"
        if loc is not None:
            fault_type += f" (~{loc} km)"
    elif i0i1 and i0i1 > 0.2:
        fault_type = f"Ground fault (SLG/LLG) near {bus_id}"
    elif i2i1 and i2i1 > 0.2:
        fault_type = f"Unbalanced phase fault near {bus_id}"
    elif min_va is not None and min_va < 0.5:
        fault_type = f"Balanced three-phase fault near {bus_id}"
    else:
        fault_type = f"Disturbance on {feeder} near {bus_id}"

    kb_results = kb_retrieve_impl(query=f"{fault_type} protection {feeder}", k=1)
    kb_citations: list[dict[str, Any]] = []
    if kb_results:
        doc = kb_results[0]
        kb_citations.append(
            {
                "source_id": doc.get("source_id", "unknown"),
                "title": doc.get("title", "Unknown SOP"),
                "section": doc.get("section"),
                "url": doc.get("url"),
                "snippet": (doc.get("snippet") or "")[:600],
            }
        )

    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "ticket_id": f"LOCAL-{incident_id}",
        "scenario": f"feeder:{feeder}",
        "bus_id": bus_id,
        "fault_type": fault_type,
        "severity": severity,
        "status": "diagnosed",
        "summary": (
            f"In local mode, the event detector flagged a {severity}-severity fault on "
            f"feeder {feeder}, most disturbed at {bus_id}. Generated without an LLM."
        ),
        "root_cause": (
            "Inferred from the per-bus fault signature (sequence ratios + voltage sag). "
            "Refer to the cited SOP for detailed protection guidance."
        ),
        "recommended_actions": [
            f"Inspect {bus_id} and its protection zone on feeder {feeder}.",
            "Confirm the fault type against relay event records and SCADA traces.",
            "Follow the cited SOP for isolation, switching, and restoration steps.",
            "Escalate to protection engineering if the signature is inconsistent with settings.",
        ],
        "evidence": [
            {
                "start_timestamp": now,
                "end_timestamp": now,
                "metric": "voltage",
                "description": (
                    f"Most-disturbed bus {bus_id}: minVa={min_va}, "
                    f"max_I0_I1={i0i1}, max_I2_I1={i2i1}."
                ),
            }
        ],
        "kb_citations": kb_citations,
        "created_at": now,
    }


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------


def run_fault_diagnosis(detection: dict[str, Any]) -> dict[str, Any]:
    """
    Coordinator entrypoint (detection-as-trigger).

    `detection` is an anomalies.detected payload (or an equivalent manual body):
    feeder, verdict{severity, anomalyScore}, and topBuses[] with per-bus signature.

    - Without Azure configured, returns a locally constructed FaultTicket.
    - With Azure configured, drives the agent graph (kb_retrieve + LLM) to produce
      a validated FaultTicket from the detection signature.
    """
    if _should_use_local():
        return _build_local_fault_ticket(detection)

    feeder, severity, score, top_buses, incident_id = _read_detection(detection)
    summary = _detection_summary(feeder, severity, score, top_buses)

    classification = detection.get("classification")
    if classification:
        summary += (
            "\n\nSupervised classifier (Family 1): "
            f"fault_type={classification.get('fault_type')}, "
            f"category={classification.get('fault_category')}, "
            f"location_km={classification.get('location_km')}"
        )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "A fault was detected. Diagnose it from the detection result below, "
                "retrieve the relevant SOP(s) with kb_retrieve, and return ONLY a single "
                "JSON object matching the FaultTicket schema.\n\n"
                f"{summary}"
            )
        ),
    ]

    try:
        final_state = _get_graph().invoke({"messages": messages})
    except LLMBudgetExceeded:
        # Budget ran out partway through the ReAct loop: stop spending and return
        # a locally built ticket instead of a partial/failed one.
        return _build_local_fault_ticket(detection)

    final_message = final_state["messages"][-1]
    try:
        ticket = _coerce_to_ticket(final_message.content)
    except (ValueError, json.JSONDecodeError):
        # The LLM returned a non-JSON or truncated/malformed object (e.g. the
        # ticket was cut off by LLM_MAX_OUTPUT_TOKENS). Don't crash the handler
        # into the DLQ and lose the incident — fall back to the local ticket.
        logger.warning(
            "Coordinator returned unparseable ticket for %s; using local fallback. "
            "If this is truncation, raise LLM_MAX_OUTPUT_TOKENS.",
            incident_id,
        )
        return _build_local_fault_ticket(detection)
    ticket.setdefault("ticket_id", incident_id)
    return ticket
