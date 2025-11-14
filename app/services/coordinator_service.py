# app/services/coordinator_service.py

import os
from datetime import datetime
from typing import Dict, Any, List

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.tools import detect_signal, kb_retrieve  # your tool definitions
from app.rag.retriever import kb_retrieve_impl           # direct KB retrieval for local mode

# -------------------------------------------------------------------
# Environment: choose between real LLM and local/offline fallback
# -------------------------------------------------------------------

APP_ENV = os.getenv("APP_ENV", "local").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

USE_LOCAL_FALLBACK = APP_ENV == "local" or not OPENAI_API_KEY or OPENAI_API_KEY == "changeme"


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


def _make_llm():
    """Create the real LLM bound with tools, only when not in local fallback mode."""
    if USE_LOCAL_FALLBACK:
        # Local/offline mode: we do not create a ChatOpenAI instance at all.
        return None

    return ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0,
    ).bind_tools([detect_signal, kb_retrieve])


_llm = _make_llm()


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

    # Basic evidence placeholder (we're not calling detect_signal here to avoid coupling)
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

    if USE_LOCAL_FALLBACK or _llm is None:
        # Local/offline dev path: no OpenAI API, no LLM calls.
        return _build_local_fault_ticket(scenario, bus_id, window_sec)

    # Real LLM path (for when you later set a valid OPENAI_API_KEY and APP_ENV!=local)
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

    result = _llm.invoke(messages)
    # Assuming result.content is a parsed JSON dict in your current setup.
    # If it's a string, you can json.loads() it here.
    ticket_dict = result.content  # type: ignore[assignment]

    # Optionally, you can validate against a Pydantic model here.
    return ticket_dict
