import json
import os
from datetime import datetime
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.models.fault_ticket import FaultTicket
from app.rag.retriever import kb_retrieve_impl           # direct KB retrieval for local mode

# -------------------------------------------------------------------
# Environment: choose between real LLM and local/offline fallback
# -------------------------------------------------------------------

APP_ENV = os.getenv("APP_ENV", "local").lower()

# The agent runs against Azure OpenAI (gpt-4o-mini deployment). We fall back to the
# offline heuristic ticket only when Azure is not configured - NOT on APP_ENV, so a
# fully-configured Azure endpoint works even with APP_ENV=local during development.
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")

USE_LOCAL_FALLBACK = (
    not AZURE_OPENAI_API_KEY
    or AZURE_OPENAI_API_KEY == "changeme"
    or not AZURE_OPENAI_ENDPOINT
    or "<your-resource>" in AZURE_OPENAI_ENDPOINT
    or not AZURE_OPENAI_DEPLOYMENT
)


SYSTEM_PROMPT = """
You are the MAFD Coordinator Agent.

Your job is to:
- Analyze anomaly signals from protection/SCADA data.
- Retrieve relevant SOP guidance from the knowledge base.
- Produce a single FaultTicket JSON object with clear, operational guidance.

TOOLS YOU MUST USE

1) detect_signal(scenario, bus_id, window_sec)
   - Always call this first.
   - It returns anomaly windows and summary statistics for the requested scenario and bus.

2) kb_retrieve(query, k)
   - Use this after you have a hypothesis about the fault.
   - The query should mention the suspected fault type, relevant equipment, and any key symptoms.

WORKFLOW (ALWAYS FOLLOW THIS ORDER)

1) Call detect_signal to obtain:
   - Anomaly windows (timestamps, affected metric).
   - Any summary metrics (counts, anomaly rate, etc.).

2) Based on the anomalies, infer:
   - A plausible fault_type (for example: overload trip, miscoordination, suspected theft-related overload).
   - The severity (low, medium, high) based on duration and intensity of anomalies.

3) Form a focused query and call kb_retrieve.
   - Mention the fault_type and the affected bus/equipment.
   - Example: "feeder overload thermal protection on bus_1 with sustained current above rating".

4) Use the returned SOP snippets to:
   - Support your root_cause reasoning with at least one citation.
   - Propose recommended_actions that follow the SOP guidance.

OUTPUT REQUIREMENTS

Return ONLY one JSON object that matches the FaultTicket schema with these fields:

- ticket_id: string
- scenario: string
- bus_id: string
- fault_type: string
- severity: one of ["low", "medium", "high"]
- status: string (e.g. "diagnosed")
- summary: concise 2–3 sentence overview of what happened
- root_cause: concise explanation of the cause
- recommended_actions: list of 3–7 short actionable steps
- evidence: list of EvidenceWindow objects:
  - start_timestamp: ISO-8601 string
  - end_timestamp: ISO-8601 string
  - metric: e.g. "current", "voltage", "frequency"
  - description: short text
- kb_citations: list of KBCitation objects:
  - source_id: from SOP metadata
  - title: SOP title
  - section: SOP section
  - url: SOP URL
  - snippet: short supporting text
- created_at: ISO-8601 timestamp

STRICT RULES

- Do not wrap the JSON in markdown. Return raw JSON only.
"""


# Lazily-built agent graph (LLM + real tools + ReAct loop). Only constructed in
# non-local mode, so importing this module never requires an OpenAI API key.
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        from app.agents.coordinator import build_coordinator_graph
        _graph = build_coordinator_graph()
    return _graph


def _coerce_to_ticket(raw: Any) -> Dict[str, Any]:
    """
    Turn the LLM's final message into a validated FaultTicket dict.

    Accepts either a dict or a string (possibly wrapped in markdown / prose),
    extracts the JSON object, and best-effort validates it against the
    FaultTicket schema without crashing the request if a field is slightly off.
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
        # Keep the data so the demo still returns something, but flag the gap.
        data.setdefault("_validation_warning", str(exc))

    return data


# -------------------------------------------------------------------
# Local/offline fallback (no OpenAI calls)
# -------------------------------------------------------------------

def _build_local_fault_ticket(scenario: str, bus_id: str, window_sec: int) -> Dict[str, Any]:
    """
    Local fallback: build a plausible FaultTicket using simple logic + KB retrieval,
    without calling any LLM or external API.
    """

    # Very simple heuristic fault_type and severity for overload_trip
    if scenario == "overload_trip":
        fault_type = f"Overload Trip on {bus_id}"
        severity = "high"
    else:
        fault_type = f"Detected anomaly in scenario '{scenario}' on {bus_id}"
        severity = "medium"

    # Basic evidence placeholder
    now = datetime.utcnow()
    start_ts = (now.replace(microsecond=0).isoformat() + "Z")
    end_ts = start_ts

    evidence: List[Dict[str, Any]] = [
        {
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
            "metric": "current",
            "description": f"Local-mode placeholder evidence window for scenario '{scenario}' on {bus_id}.",
        }
    ]

    # Use KB directly to get at least one real citation
    kb_results = kb_retrieve_impl(
        query=f"feeder overload thermal protection {bus_id}",
        k=1,
    )

    kb_citations: List[Dict[str, Any]] = []
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

    ticket_id = f"LOCAL-{scenario}-{bus_id}"

    summary = (
        f"In local mode, an anomaly consistent with {fault_type} was detected on {bus_id}. "
        f"This ticket was generated without calling an external LLM."
    )

    root_cause = (
        "Potential overload condition inferred from the scenario label and configuration. "
        "Refer to the cited SOP for detailed overload and protection guidance."
    )

    recommended_actions = [
        "Verify feeder loading and confirm whether current is above normal operating limits.",
        "Review recent operational changes or load transfers on the affected feeder.",
        "Consult the cited SOP and confirm that relay settings match the latest coordination study.",
        "If overload conditions persist, coordinate with planning/protection engineering for longer-term mitigation.",
    ]

    ticket: Dict[str, Any] = {
        "ticket_id": ticket_id,
        "scenario": scenario,
        "bus_id": bus_id,
        "fault_type": fault_type,
        "severity": severity,
        "status": "diagnosed",
        "summary": summary,
        "root_cause": root_cause,
        "recommended_actions": recommended_actions,
        "evidence": evidence,
        "kb_citations": kb_citations,
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }

    return ticket


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------

def run_fault_diagnosis(scenario: str, bus_id: str, window_sec: int = 300) -> Dict[str, Any]:
    """
    Main coordinator entrypoint.

    - In local mode (APP_ENV=local or OPENAI_API_KEY missing/changeme), returns a
      locally constructed FaultTicket without using OpenAI.
    - In non-local mode, delegates to the LLM with tool calling.
    """

    if USE_LOCAL_FALLBACK:
        # Local/offline dev path: no OpenAI API, no LLM calls.
        return _build_local_fault_ticket(scenario, bus_id, window_sec)

    # Real LLM path: drive the agent graph (LLM + real detector/RAG tools + loop).
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Diagnose the fault for scenario '{scenario}' on bus '{bus_id}' "
                f"using a {window_sec}-second window. "
                "Call the tools detect_signal and kb_retrieve as needed and return "
                "ONLY a single JSON object that matches the FaultTicket schema."
            )
        ),
    ]

    final_state = _get_graph().invoke({"messages": messages})
    final_message = final_state["messages"][-1]
    return _coerce_to_ticket(final_message.content)
