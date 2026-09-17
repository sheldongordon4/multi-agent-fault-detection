import json
import logging
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.faults import budget
from app.faults.budget import LLMBudgetExceeded
from app.faults.config import settings as faults_settings
from app.faults.constants import FAULT_QUERY_TERMS, SYSTEM_PROMPT
from app.faults.customers import customers_affected, impact_share
from app.faults.schemas import FaultTicket
from app.rag.retriever import kb_retrieve_impl
from app.utils import message_text  # direct KB retrieval for local mode

logger = logging.getLogger(__name__)

# Fall back to the offline heuristic ticket only when no LLM endpoint is
# configured (not on APP_ENV), so a configured endpoint works even with
# APP_ENV=local in dev.
USE_LOCAL_FALLBACK = not faults_settings.llm_configured


def _should_use_local() -> bool:
    """
    Use the local (no-LLM) fallback when no endpoint is configured OR the process
    endpoint-call budget is spent. The budget check makes the switch permanent
    once we hit the cap, so no further endpoint calls are attempted.
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


def _detection_window(detection: dict[str, Any]) -> tuple[str | None, str | None]:
    """The extraction window this incident was reduced from, if it carried one."""
    return detection.get("windowStart") or detection.get("window_start"), detection.get(
        "windowEnd"
    ) or detection.get("window_end")


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


def _now_iso() -> str:
    """UTC now, second precision, Z-suffixed — the one timestamp format tickets use."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_to_ticket(raw: Any) -> dict[str, Any]:
    """
    Turn the LLM's final message into a validated FaultTicket dict.

    Accepts a dict or a string (possibly wrapped in prose), extracts the JSON
    object, and validates it against the FaultTicket schema.
    """
    if isinstance(raw, dict):
        data = raw
    else:
        text = message_text(raw)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"LLM did not return a JSON object: {text[:200]}")
        data = json.loads(text[start : end + 1])

    try:
        return FaultTicket.model_validate(data).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"LLM returned an invalid FaultTicket: {exc}") from exc


# -------------------------------------------------------------------
# Local/offline fallback (no LLM calls)
# -------------------------------------------------------------------


def _kb_query(fault_type: str, feeder: str) -> str:
    """
    Turn a fault label into a query the SOP knowledge base can actually match.

    `fault_type` arrives as either a classifier code with context ("SLG near b671
    (~0.4 km)") or a heuristic phrase ("Ground fault (SLG/LLG) near b671"). The
    bare codes retrieve badly on their own — see FAULT_QUERY_TERMS — so a
    recognised leading code is expanded into its physical description. Anything
    unrecognised is passed through, which keeps the heuristic phrases working
    since they are already descriptive.

    The suffix is deliberately just "feeder <id>", not "on distribution feeder
    <id>": the extra word "distribution" measurably biased retrieval toward
    whichever SOPs happened to use it, and was enough on its own to send an LL
    fault to the open-conductor procedure.
    """
    code = fault_type.strip().split()[0].upper() if fault_type.strip() else ""
    described = FAULT_QUERY_TERMS.get(code)
    if described:
        return f"{described} feeder {feeder}"
    return f"{fault_type} protection {feeder}"


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

    kb_results = kb_retrieve_impl(query=_kb_query(fault_type, feeder), k=1)
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

    now = _now_iso()
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


def _pin_server_facts(ticket: dict[str, Any], detection: dict[str, Any]) -> dict[str, Any]:
    """
    Overwrite every ticket field the pipeline already knows.

    The LLM fills in the whole schema whether or not it has grounds to. Where a
    value is a measurement or an identifier, its guess is not a second opinion —
    it is a wrong answer that looks authoritative. Each of these was observed:

      - `ticket_id`: the model wrote "TICK-IEEE13-001" on EVERY incident, so
        two distinct faults carried one id. `incident_id` is the idempotency
        key the whole pipeline is built on (persistence upserts by it), and an
        id the model invents is not that key.
      - `severity`: the detector computes it from the anomaly score, and
        `app/assignments` derives priority and SLA from it. A model that
        rewrites severity silently re-triages the work queue.
      - `scenario`: purely `feeder:<id>`, which is in the payload.
      - `bus_id`: the bus an operator gets dispatched to, and the input to
        `customers_affected`. Model-chosen, it landed on b675 — whose testbed
        row reports max_Ia = 0 alongside I0/I1 ~ 2.0, an export artifact the
        model reads as the strongest ground signature on the feeder. Same
        fault, 980 customers instead of 6,400.
      - evidence timestamps: the model dated a 2026 incident to 2023. The real
        window is measured by the extraction worker and rides on the event.

    Deliberately NOT pinned: `fault_type`, `summary`, `root_cause`,
    `recommended_actions`. Those are the interpretation the LLM is here to
    produce.
    """
    feeder, severity, _score, top_buses, incident_id = _read_detection(detection)

    ticket["ticket_id"] = incident_id
    ticket["severity"] = severity
    ticket["scenario"] = f"feeder:{feeder}"
    if top_buses:
        ticket["bus_id"] = top_buses[0].get("bus") or ticket.get("bus_id")

    window_start, window_end = _detection_window(detection)
    if window_start and window_end:
        for window in ticket.get("evidence") or []:
            if isinstance(window, dict):
                window["start_timestamp"] = window_start
                window["end_timestamp"] = window_end

    return ticket


def _enrich_ticket(ticket: dict[str, Any], detection: dict[str, Any]) -> dict[str, Any]:
    """
    Attach what the pipeline measured, after the ticket has been written.

    Same reasoning as `_restore_citation_snippets` directly below: these are
    facts the detection payload already carries, and letting the LLM restate
    them turns a measurement into a paraphrase. Three of them in particular
    must never be model output —

      - `fault_type_confidence` is the classifier's own probability. An invented
        one would be confidently wrong precisely where the classifier is
        uncertain, which is the only situation it exists to expose.
      - `customers_affected` is a dispatch input. An operator ranks work by it.
      - `attribution` is the explanation of the verdict; generated prose about
        the evidence is exactly what it is meant to replace.

    Enrichment is best-effort. A ticket with no classification, an unmodelled
    bus, or no attribution baseline is still a valid ticket, so every field
    stays absent rather than guessed.
    """
    classification = detection.get("classification") or {}

    confidence = classification.get("confidence")
    if confidence is not None:
        ticket["fault_type_confidence"] = confidence
    alternatives = classification.get("alternatives")
    if alternatives:
        ticket["fault_type_alternatives"] = alternatives

    attribution = detection.get("attribution")
    if attribution:
        ticket["attribution"] = attribution

    # Read from the ticket, not the detection. These now agree — _pin_server_facts
    # sets bus_id from the detection ranking before this runs — but the ticket
    # stays the source of truth, because the bus the ticket NAMES is the one an
    # operator is dispatched to, and the count must describe that bus.
    bus_id = ticket.get("bus_id")
    count = customers_affected(bus_id)
    if count is not None:
        ticket["customers_affected"] = count
        ticket["customers_share"] = impact_share(bus_id)

    return ticket


def _restore_citation_snippets(ticket: dict[str, Any]) -> dict[str, Any]:
    """
    Replace each citation's snippet with the authoritative KB text for its id.

    The agent composes the ticket, including `kb_citations`, so whatever it
    writes into `snippet` is model output — paraphrased, truncated, or invented.
    Two reasons that is not acceptable:

      - the SOP bodies open with a SYNTHETIC REFERENCE provenance notice saying
        they are generated references and not approved utility procedures. The
        agent drops it, so the caveat silently disappears from exactly the place
        an operator would read it.
      - Agent_Prompt_Guide.md already forbids fabricating citations. A snippet
        the model wrote is a fabricated quotation of a real document, which is
        harder to catch than a fabricated source id.

    So the id and title stay as the agent chose them, and the quoted text comes
    from the knowledge base. A citation whose id matches nothing in the KB is
    dropped rather than shown with unverifiable text.
    """
    citations = ticket.get("kb_citations")
    if not isinstance(citations, list) or not citations:
        return ticket

    verified: list[dict[str, Any]] = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        source_id = str(citation.get("source_id") or "").strip()
        if not source_id:
            continue

        docs = kb_retrieve_impl(query=source_id, k=3)
        match = next((d for d in docs if d.get("source_id") == source_id), None)
        if match is None:
            logger.warning(
                "Dropping citation %s: no such document in the SOP knowledge base",
                source_id,
            )
            continue

        verified.append(
            {
                **citation,
                "title": match.get("title") or citation.get("title"),
                "section": match.get("section") or citation.get("section"),
                "url": match.get("url") or citation.get("url"),
                "snippet": (match.get("snippet") or "")[:600],
            }
        )

    ticket["kb_citations"] = verified
    return ticket


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
        return _enrich_ticket(_build_local_fault_ticket(detection), detection)

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
        return _enrich_ticket(_build_local_fault_ticket(detection), detection)

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
        return _enrich_ticket(_build_local_fault_ticket(detection), detection)
    # Creation time is the server's to state, never the model's: it writes this
    # field whether or not it knows the time, and what it writes is its
    # training-era guess — observed as a 2023 date on a ticket raised in 2026.
    ticket["created_at"] = _now_iso()
    ticket = _pin_server_facts(ticket, detection)
    return _enrich_ticket(_restore_citation_snippets(ticket), detection)
