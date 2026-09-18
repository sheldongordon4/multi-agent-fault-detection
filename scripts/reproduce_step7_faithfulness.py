"""
reproduce_step7_faithfulness.py
================================
Evaluates Layer 2 (RAG diagnostic agent) faithfulness for the MAFD paper.

Produces:
    - Context Precision and Context Recall (TF-IDF retrieval, same as Table 6)
    - Faithfulness Score: fraction of generated claims grounded in retrieved SOPs
    - Hallucination Rate: 1 - Faithfulness Score
    - Full per-scenario results saved to results/faithfulness_evaluation_<N>.json
      (N = next free number; earlier runs are never overwritten)

Paper section:  5.8 (extends Table 6 with faithfulness metrics)

Methodology:
    1. For each of 24 fault diagnostic scenarios, retrieve the top-2 relevant
       SOPs using TF-IDF (conservative proxy for ChromaDB dense retrieval).
    2. Pass the retrieved SOPs + detection payload to the Azure OpenAI endpoint
       to generate a FaultTicket (same prompt as the deployed coordinator agent).
    3. Use the same Azure endpoint as a judge. It is shown EXACTLY what the
       generator saw (the detection payload and the full retrieved SOP text)
       and scores each summary / root_cause claim as grounded or not. A claim
       is grounded if it restates the detection payload, is stated in the SOPs,
       or applies an SOP signature rule to the detection values.
    4. Faithfulness = mean fraction of claims judged as grounded across scenarios
       (scenarios whose judge call fails are excluded, not scored as 0).
    5. Hallucination Rate = 1 - Faithfulness Score.

If Azure credentials are not yet configured, the script runs the local heuristic
fallback path instead and reports a clearly labelled LOCAL HEURISTIC result,
which gives a lower bound on citation accuracy without LLM calls.

Prerequisites:
    pip install openai
    .env file with Azure credentials (see .env.example):
        AZURE_OPENAI_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
        AZURE_OPENAI_API_KEY=<your-key>
        AZURE_OPENAI_DEPLOYMENT=<your-deployment-name>
    data/sop/ directory with the SOP markdown files (see docs/Knowledge_Base_Index.md).

Usage:
    python scripts/reproduce_step7_faithfulness.py
    python scripts/reproduce_step7_faithfulness.py --scenarios 10  # quick test
    python scripts/reproduce_step7_faithfulness.py --local-only     # no LLM calls
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")

SOP_DIR     = REPO_ROOT / "data" / "sop"
RESULTS_DIR = REPO_ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Azure config (loaded from .env) ──────────────────────────────────────────
AZURE_ENDPOINT   = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_API_KEY    = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")

# Same knobs the coordinator uses (app/faults/agent.py), minus the rate limiter.
LLM_MAX_RETRIES     = int(os.getenv("LLM_MAX_RETRIES", "2"))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

TOP_K = 2  # SOPs retrieved per query (matches deployed system)

SYSTEM_PROMPT = """\
You are the MAFD Coordinator Agent.

An unsupervised detector has ALREADY flagged a fault on a distribution feeder and
handed you its result. You do NOT run detection yourself. Your job is to:
- Interpret the detection result (the most-disturbed buses and their electrical
  signature) to infer a plausible fault_type.
- Use the provided SOP context to support root_cause and recommended_actions.
- Produce a single FaultTicket JSON object with clear, operational guidance.

INTERPRETING THE SIGNATURE (per-bus features in the detection result)
- High zero-sequence ratio (max_I0_I1) => GROUND involvement (SLG / LLG).
- High negative-sequence ratio (max_I2_I1) => UNBALANCE (SLG, LL, LLG).
- Both ratios near zero with a deep voltage sag (low minVa) => balanced 3-phase fault.
- Sustained high current (maxIa) with only a modest sag => overload-type condition.

OUTPUT REQUIREMENTS
Return ONLY one valid JSON object with these exact fields:
{
  "ticket_id": "<string>",
  "scenario": "<feeder id>",
  "bus_id": "<most disturbed bus>",
  "fault_type": "<inferred fault type>",
  "severity": "<low|medium|high>",
  "status": "diagnosed",
  "summary": "<2-3 sentence overview>",
  "root_cause": "<explanation with SOP reference>",
  "recommended_actions": ["<action 1>", "..."],
  "evidence": [{"start_timestamp": "<ISO>", "end_timestamp": "<ISO>",
                "metric": "<voltage|current>", "description": "<text>"}],
  "kb_citations": [{"source_id": "<SOP-ID>", "title": "<SOP title>",
                    "section": "<section>", "snippet": "<brief quote>"}]
}
"""

JUDGE_PROMPT_TEMPLATE = """\
You are a faithfulness evaluator for a power distribution fault diagnostic system.

An AI agent was given two inputs — (a) a DETECTION RESULT from an upstream fault
detector and (b) the SOP CONTEXT below — and produced the diagnostic summary and
root cause shown. Assess whether each claim in the generated text is grounded in
what the agent was actually given.

DETECTION RESULT PROVIDED TO THE AGENT:
{detection}

SOP CONTEXT PROVIDED TO THE AGENT:
{sop_context}

GENERATED SUMMARY:
{summary}

GENERATED ROOT CAUSE:
{root_cause}

TASK:
1. List each distinct factual claim in the summary and root cause.
2. Mark each claim GROUNDED or NOT GROUNDED:
   - GROUNDED: it restates a value from the detection result (feeder, bus id,
     severity, minVa / maxIa / maxI0I1 / maxI2I1); OR it is stated in the SOP
     context; OR it applies a signature rule stated in the SOP context to the
     detection values (e.g. the SOP says elevated I0/I1 indicates ground
     involvement and the detection result shows elevated maxI0I1).
   - NOT GROUNDED: it introduces facts, causes, equipment, or procedures that
     appear in neither input, or it contradicts either input.
3. Return ONLY a JSON object with this exact structure:
{{
  "total_claims": <integer>,
  "grounded_claims": <integer>,
  "faithfulness_score": <grounded_claims / total_claims, float between 0 and 1>,
  "ungrounded_examples": ["<claim text>", "..."]
}}
"""

# ── 24 evaluation scenarios ───────────────────────────────────────────────────
# Relevant SOPs per fault type: the fault-type SOP itself plus the SOP its own
# Notes cross-reference (SLG-005 -> HIZ-010, LL-006 -> LLG-007, OPEN-009 -> HIZ-010).
GROUND_TRUTH: dict[str, list[str]] = {
    "SLG":      ["SOP-SLG-005", "SOP-HIZ-010"],
    "LL":       ["SOP-LL-006", "SOP-LLG-007"],
    "LLG":      ["SOP-LLG-007", "SOP-LL-006"],
    "LLL":      ["SOP-3PH-008"],
    "LLLG":     ["SOP-3PH-008"],
    "OPEN_1PH": ["SOP-OPEN-009", "SOP-HIZ-010"],
    "OPEN_2PH": ["SOP-OPEN-009", "SOP-HIZ-010"],
    "OPEN_3PH": ["SOP-OPEN-009", "SOP-HIZ-010"],
    "OVERLOAD": ["SOP-OVLD-001", "SOP-THFT-003"],
}

# Queries name the suspected fault type, its sequence-ratio signature, and the
# bus — the same shape the deployed coordinator's kb_retrieve query takes.

SCENARIOS = [
    {"id": "T01", "fault_type": "SLG", "feeder": "ieee13", "bus": "b650",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.72,
                 "top_buses": [{"bus": "b650", "minVa": 0.021, "maxIa": 6.12,
                                "maxI0I1": 0.994, "maxI2I1": 0.12}]},
     "query": "single line-to-ground fault SLG one phase voltage collapse elevated zero-sequence ratio I0/I1 ground overcurrent bus b650"},
    {"id": "T02", "fault_type": "SLG", "feeder": "ieee13", "bus": "b632",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.68,
                 "top_buses": [{"bus": "b632", "minVa": 0.045, "maxIa": 5.80,
                                "maxI0I1": 0.88, "maxI2I1": 0.09}]},
     "query": "SLG ground fault high I0/I1 one phase depressed ground element operation recloser lockout bus b632"},
    {"id": "T03", "fault_type": "SLG", "feeder": "ieee13", "bus": "b671",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.71,
                 "top_buses": [{"bus": "b671", "minVa": 0.032, "maxIa": 5.50,
                                "maxI0I1": 0.91, "maxI2I1": 0.11}]},
     "query": "single phase to ground fault zero-sequence current ground involvement downed conductor patrol bus b671"},
    {"id": "T04", "fault_type": "LL", "feeder": "ieee13", "bus": "b650",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.65,
                 "top_buses": [{"bus": "b650", "minVa": 0.18, "maxIa": 4.20,
                                "maxI0I1": 0.007, "maxI2I1": 0.51}]},
     "query": "phase-to-phase fault LL two phases depressed negative-sequence I2/I1 elevated no ground path bus b650"},
    {"id": "T05", "fault_type": "LL", "feeder": "ieee13", "bus": "b632",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.63,
                 "top_buses": [{"bus": "b632", "minVa": 0.21, "maxIa": 3.90,
                                "maxI0I1": 0.006, "maxI2I1": 0.48}]},
     "query": "line-to-line fault I2/I1 elevated I0/I1 low no ground element operation conductor-to-conductor contact bus b632"},
    {"id": "T06", "fault_type": "LL", "feeder": "ieee13", "bus": "b671",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.61,
                 "top_buses": [{"bus": "b671", "minVa": 0.19, "maxIa": 4.10,
                                "maxI0I1": 0.008, "maxI2I1": 0.49}]},
     "query": "LL fault two phase conductors in contact phase overcurrent no ground involvement conductor slap bus b671"},
    {"id": "T07", "fault_type": "LLG", "feeder": "ieee13", "bus": "b650",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.69,
                 "top_buses": [{"bus": "b650", "minVa": 0.09, "maxIa": 5.20,
                                "maxI0I1": 0.51, "maxI2I1": 0.46}]},
     "query": "double line-to-ground fault LLG two phases collapse both zero-sequence and negative-sequence elevated bus b650"},
    {"id": "T08", "fault_type": "LLG", "feeder": "ieee13", "bus": "b632",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.67,
                 "top_buses": [{"bus": "b632", "minVa": 0.11, "maxIa": 4.95,
                                "maxI0I1": 0.49, "maxI2I1": 0.44}]},
     "query": "LLG fault two phases and ground I0/I1 and I2/I1 both elevated phase and ground elements operated bus b632"},
    {"id": "T09", "fault_type": "LLL", "feeder": "ieee13", "bus": "b650",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.58,
                 "top_buses": [{"bus": "b650", "minVa": 0.05, "maxIa": 7.20,
                                "maxI0I1": 0.003, "maxI2I1": 0.004}]},
     "query": "balanced three-phase fault LLL all three phases collapse deep sag sequence ratios near zero bus b650"},
    {"id": "T10", "fault_type": "LLL", "feeder": "ieee13", "bus": "b632",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.56,
                 "top_buses": [{"bus": "b632", "minVa": 0.07, "maxIa": 6.80,
                                "maxI0I1": 0.002, "maxI2I1": 0.003}]},
     "query": "three phase symmetrical fault LLL highest fault current balanced deep sag no sequence unbalance bus b632"},
    {"id": "T11", "fault_type": "LLLG", "feeder": "ieee13", "bus": "b650",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.78,
                 "top_buses": [{"bus": "b650", "minVa": 0.03, "maxIa": 8.10,
                                "maxI0I1": 0.61, "maxI2I1": 0.005}]},
     "query": "three-phase-to-ground fault LLLG all phases collapse deep balanced sag ground path bus b650"},
    {"id": "T12", "fault_type": "LLLG", "feeder": "ieee13", "bus": "b632",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.76,
                 "top_buses": [{"bus": "b632", "minVa": 0.04, "maxIa": 7.90,
                                "maxI0I1": 0.59, "maxI2I1": 0.004}]},
     "query": "LLLG bolted three phase ground fault severe symmetrical sag highest fault current bus b632"},
    {"id": "T13", "fault_type": "LLLG", "feeder": "ieee13", "bus": "b671",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.74,
                 "top_buses": [{"bus": "b671", "minVa": 0.05, "maxIa": 7.60,
                                "maxI0I1": 0.57, "maxI2I1": 0.003}]},
     "query": "three phase fault with ground involvement LLLG all phases depressed switching error safety grounds bus b671"},
    {"id": "T14", "fault_type": "OPEN_1PH", "feeder": "ieee13", "bus": "b684",
     "payload": {"feeder": "ieee13", "severity": "medium", "anomaly_score": 0.31,
                 "top_buses": [{"bus": "b684", "minVa": 0.61, "maxIa": 0.18,
                                "maxI0I1": 0.22, "maxI2I1": 0.19}]},
     "query": "single phase open conductor OPEN_1PH one phase current near zero voltage present unbalance without fault current bus b684"},
    {"id": "T15", "fault_type": "OPEN_1PH", "feeder": "ieee13", "bus": "b675",
     "payload": {"feeder": "ieee13", "severity": "medium", "anomaly_score": 0.29,
                 "top_buses": [{"bus": "b675", "minVa": 0.58, "maxIa": 0.16,
                                "maxI0I1": 0.20, "maxI2I1": 0.18}]},
     "query": "open conductor single-phasing negative-sequence elevated no overcurrent operation broken conductor bus b675"},
    {"id": "T16", "fault_type": "OPEN_1PH", "feeder": "ieee13", "bus": "b632",
     "payload": {"feeder": "ieee13", "severity": "medium", "anomaly_score": 0.28,
                 "top_buses": [{"bus": "b632", "minVa": 0.60, "maxIa": 0.17,
                                "maxI0I1": 0.21, "maxI2I1": 0.17}]},
     "query": "one phase open series fault blown fuse on one phase backfeed downstream three-phase customers bus b632"},
    {"id": "T17", "fault_type": "OPEN_2PH", "feeder": "ieee13", "bus": "b650",
     "payload": {"feeder": "ieee13", "severity": "medium", "anomaly_score": 0.38,
                 "top_buses": [{"bus": "b650", "minVa": 0.41, "maxIa": 0.22,
                                "maxI0I1": 0.31, "maxI2I1": 0.28}]},
     "query": "two phase open conductor OPEN_2PH two phases current lost severe unbalance no trip bus b650"},
    {"id": "T18", "fault_type": "OPEN_2PH", "feeder": "ieee13", "bus": "b671",
     "payload": {"feeder": "ieee13", "severity": "medium", "anomaly_score": 0.36,
                 "top_buses": [{"bus": "b671", "minVa": 0.44, "maxIa": 0.20,
                                "maxI0I1": 0.29, "maxI2I1": 0.26}]},
     "query": "double open phase series fault two conductors interrupted single-phasing partial outage bus b671"},
    {"id": "T19", "fault_type": "OPEN_3PH", "feeder": "ieee13", "bus": "b650",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.52,
                 "top_buses": [{"bus": "b650", "minVa": 0.08, "maxIa": 0.11,
                                "maxI0I1": 0.41, "maxI2I1": 0.38}]},
     "query": "three phase open conductor OPEN_3PH all phases interrupted loss of supply no short circuit bus b650"},
    {"id": "T20", "fault_type": "OPEN_3PH", "feeder": "ieee13", "bus": "b632",
     "payload": {"feeder": "ieee13", "severity": "high", "anomaly_score": 0.50,
                 "top_buses": [{"bus": "b632", "minVa": 0.09, "maxIa": 0.10,
                                "maxI0I1": 0.39, "maxI2I1": 0.36}]},
     "query": "complete three phase open all phases lost switch pole failed to close loss of supply bus b632"},
    {"id": "T21", "fault_type": "OVERLOAD", "feeder": "ieee13", "bus": "b650",
     "payload": {"feeder": "ieee13", "severity": "medium", "anomaly_score": 0.22,
                 "top_buses": [{"bus": "b650", "minVa": 0.88, "maxIa": 1.15,
                                "maxI0I1": 0.003, "maxI2I1": 0.002}]},
     "query": "feeder overload sustained current above thermal rating continuous load 100 percent trip criteria time-current"},
    {"id": "T22", "fault_type": "OVERLOAD", "feeder": "ieee13", "bus": "b632",
     "payload": {"feeder": "ieee13", "severity": "medium", "anomaly_score": 0.19,
                 "top_buses": [{"bus": "b632", "minVa": 0.90, "maxIa": 1.08,
                                "maxI0I1": 0.002, "maxI2I1": 0.002}]},
     "query": "thermal overload feeder current trending above 80 percent rating gradual heating SCADA monitoring"},
    {"id": "T23", "fault_type": "OVERLOAD", "feeder": "ieee13", "bus": "b671",
     "payload": {"feeder": "ieee13", "severity": "low", "anomaly_score": 0.15,
                 "top_buses": [{"bus": "b671", "minVa": 0.93, "maxIa": 0.98,
                                "maxI0I1": 0.001, "maxI2I1": 0.001}]},
     "query": "suspected theft irregular load pattern overload without billing growth non-technical loss revenue"},
    {"id": "T24", "fault_type": "OVERLOAD", "feeder": "ieee13", "bus": "b684",
     "payload": {"feeder": "ieee13", "severity": "low", "anomaly_score": 0.14,
                 "top_buses": [{"bus": "b684", "minVa": 0.94, "maxIa": 0.95,
                                "maxI0I1": 0.001, "maxI2I1": 0.001}]},
     "query": "unauthorized connection suspected overload persistent high loading no corresponding billed demand theft investigation"},
]


# ── TF-IDF retrieval (same as reproduce_step6) ────────────────────────────────
def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())

def _tf(tokens: list[str]) -> dict[str, float]:
    counts: dict[str, int] = defaultdict(int)
    for t in tokens:
        counts[t] += 1
    n = len(tokens)
    return {k: v / n for k, v in counts.items()}

def _idf(corpus: list[list[str]]) -> dict[str, float]:
    n = len(corpus)
    df: dict[str, int] = defaultdict(int)
    for doc in corpus:
        for term in set(doc):
            df[term] += 1
    return {term: math.log(n / (1 + count)) for term, count in df.items()}

def _tfidf_score(q_tokens: list[str], d_tokens: list[str],
                 idf_map: dict[str, float]) -> float:
    q_tf = _tf(q_tokens)
    d_tf = _tf(d_tokens)
    return sum(q_tf[t] * d_tf[t] * idf_map.get(t, 0.0) for t in q_tf if t in d_tf)

def _load_sops() -> dict[str, dict]:
    sops = {}
    for f in sorted(SOP_DIR.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        m_id    = re.search(r"ID:\s*([\w-]+)", text)
        m_title = re.search(r"TITLE:\s*(.+)", text)
        if not m_id or not m_title:
            continue
        sops[m_id.group(1).strip()] = {
            "title": m_title.group(1).strip(),
            "text": text,
            "id": m_id.group(1).strip(),
        }
    return sops

def _retrieve(query: str, sops: dict, sop_ids: list, sop_tokens: list,
              idf_map: dict) -> list[dict]:
    q_tokens = _tokenize(query)
    scores = {sid: _tfidf_score(q_tokens, sop_tokens[i], idf_map)
              for i, sid in enumerate(sop_ids)}
    ranked = sorted(scores, key=scores.get, reverse=True)  # type: ignore
    return [{"id": sid, "title": sops[sid]["title"],
             "text": sops[sid]["text"]} for sid in ranked[:TOP_K]]


# ── Azure OpenAI helper ───────────────────────────────────────────────────────
def _azure_configured() -> bool:
    return bool(
        AZURE_ENDPOINT
        and "<" not in AZURE_ENDPOINT
        and AZURE_API_KEY
        and AZURE_API_KEY not in ("changeme", "")
        and AZURE_DEPLOYMENT
    )


def _v1_base_url(endpoint: str) -> str:
    """
    Normalise the configured endpoint to the OpenAI-compatible /openai/v1/ route.
    """
    root = re.sub(r"/api/projects/[^/]+/?$", "", endpoint.rstrip("/"))
    return f"{root}/openai/v1/"


def _call_azure(messages: list[dict], max_tokens: int = 1000,
                temperature: float = 0.1) -> str:
    """
    Call the deployment. Raises on failure.
    """
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(
        base_url=_v1_base_url(AZURE_ENDPOINT),
        api_key=AZURE_API_KEY,
        model=AZURE_DEPLOYMENT,
        max_retries=LLM_MAX_RETRIES,
        timeout=LLM_TIMEOUT_SECONDS,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return llm.invoke(messages).content or ""


# ── Context shared by the generator and the judge ─────────────────────────────
# Both must see the same thing: faithfulness is measured against the context
# the generator was given, so the judge cannot be shown less (or different) text.
def _detection_block(sc: dict) -> str:
    buses = sc["payload"]["top_buses"]
    bus_lines = "\n".join(
        f"  - {b['bus']}: minVa={b['minVa']}, maxIa={b['maxIa']}, "
        f"maxI0I1={b['maxI0I1']}, maxI2I1={b['maxI2I1']}"
        for b in buses
    )
    return (
        f"Feeder: {sc['payload']['feeder']}\n"
        f"Severity: {sc['payload']['severity']}\n"
        f"Anomaly score: {sc['payload']['anomaly_score']}\n"
        f"Most-disturbed buses:\n{bus_lines}"
    )


def _sop_context(retrieved: list[dict]) -> str:
    # Full SOP text. The 'Conditions' block that states each fault's
    # sequence-ratio signature sits ~600-950 chars in, after the header and
    # the SYNTHETIC REFERENCE disclaimer, so any prefix truncation drops it.
    return "\n\n".join(
        f"--- {r['title']} ({r['id']}) ---\n{r['text']}" for r in retrieved
    )


# ── Generation ────────────────────────────────────────────────────────────────
def _build_user_prompt(sc: dict, retrieved: list[dict]) -> str:
    return (
        f"DETECTION RESULT:\n{_detection_block(sc)}\n\n"
        f"RETRIEVED SOP CONTEXT:\n{_sop_context(retrieved)}\n\n"
        f"Generate a FaultTicket JSON for this fault event."
    )


def _generate_ticket_llm(sc: dict, retrieved: list[dict]) -> dict | None:
    """Call Azure LLM to generate a FaultTicket. Returns parsed dict or None."""
    user_prompt = _build_user_prompt(sc, retrieved)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]
    # 2000 tokens: with full SOP text in context the ticket runs ~1000-1500
    # tokens, and a cap-truncated JSON fails to parse.
    for attempt in (1, 2):
        try:
            raw = _call_azure(messages, max_tokens=2000)
            # Strip markdown code fences if present
            clean = re.sub(r"```(?:json)?|```", "", raw).strip()
            return json.loads(clean)
        except Exception as e:
            print(f"    [WARN] LLM generation failed for {sc['id']} (attempt {attempt}): {e}")
    return None


def _generate_ticket_local(sc: dict, retrieved: list[dict]) -> dict:
    """Heuristic fallback ticket without any LLM call."""
    buses = sc["payload"]["top_buses"]
    top = buses[0] if buses else {}
    bus_id = top.get("bus", "unknown")
    i0i1 = top.get("maxI0I1", 0.0)
    i2i1 = top.get("maxI2I1", 0.0)
    min_va = top.get("minVa", 1.0)
    if i0i1 > 0.3:
        inferred = "Ground fault (SLG/LLG) — elevated I0/I1 ratio"
    elif i2i1 > 0.3:
        inferred = "Unbalanced phase fault (LL/LLG) — elevated I2/I1 ratio"
    elif min_va < 0.2:
        inferred = "Balanced three-phase fault — deep voltage sag, near-zero sequence ratios"
    else:
        inferred = "Operational anomaly — possible overload or open-conductor condition"
    now = datetime.now(timezone.utc).isoformat()
    return {
        "ticket_id": f"LOCAL-{sc['id']}-{now}",
        "scenario": sc["payload"]["feeder"],
        "bus_id": bus_id,
        "fault_type": inferred,
        "severity": sc["payload"]["severity"],
        "status": "diagnosed",
        "summary": (
            f"Anomaly detected on feeder {sc['payload']['feeder']} at bus {bus_id}. "
            f"{inferred}. Refer to cited SOP for operator actions."
        ),
        "root_cause": (
            f"Signature analysis: I0/I1={i0i1:.3f}, I2/I1={i2i1:.3f}, "
            f"minVa={min_va:.3f} pu. Consistent with {inferred.split('—')[0].strip()}."
        ),
        "recommended_actions": [
            f"Inspect {bus_id} and its protection zone.",
            "Review SCADA relay event logs.",
            "Follow cited SOP for isolation and restoration.",
        ],
        "evidence": [{"start_timestamp": now, "end_timestamp": now,
                      "metric": "voltage", "description": f"minVa={min_va:.3f}"}],
        "kb_citations": [
            {"source_id": r["id"], "title": r["title"],
             "section": None, "snippet": r["text"][:120]}
            for r in retrieved
        ],
    }


# ── Faithfulness judge ────────────────────────────────────────────────────────
def _judge_faithfulness(ticket: dict, sc: dict, retrieved: list[dict]) -> dict | None:
    """
    Use Azure LLM as judge to score faithfulness of the generated ticket
    against the same detection payload + SOP text the generator saw.
    Returns None if the judge call fails, so the caller can exclude the
    scenario instead of counting it as fully hallucinated.
    """
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        detection=_detection_block(sc),
        sop_context=_sop_context(retrieved),
        summary=ticket.get("summary", ""),
        root_cause=ticket.get("root_cause", ""),
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        raw = _call_azure(messages, max_tokens=800, temperature=0.0)
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        result = json.loads(clean)
    except Exception as e:
        print(f"    [WARN] Judge call failed: {e}")
        return None
    # Trust the counts, not the model's arithmetic.
    total = int(result.get("total_claims") or 0)
    grounded = int(result.get("grounded_claims") or 0)
    if total > 0:
        result["faithfulness_score"] = round(grounded / total, 4)
    return result


def _local_faithfulness(ticket: dict, retrieved: list[dict]) -> dict:
    """
    Lightweight faithfulness proxy without LLM judge.
    Checks whether key terms from the SOP text appear in the generated ticket.
    This is a coverage lower bound, not a true faithfulness score.
    """
    sop_words = set()
    for r in retrieved:
        sop_words.update(_tokenize(r["text"]))
    output_text = (ticket.get("summary", "") + " " + ticket.get("root_cause", "")).lower()
    output_tokens = set(_tokenize(output_text))
    # Meaningful SOP terms (>4 chars, not stopwords)
    stopwords = {"that", "this", "with", "from", "have", "will", "been", "they",
                 "their", "which", "when", "where", "what", "more", "also",
                 "such", "each", "than", "then", "into", "only", "must"}
    meaningful_sop = {w for w in sop_words if len(w) > 4 and w not in stopwords}
    meaningful_output = {w for w in output_tokens if len(w) > 4 and w not in stopwords}
    overlap = meaningful_output & meaningful_sop
    coverage = len(overlap) / len(meaningful_output) if meaningful_output else 0.0
    return {
        "total_claims": len(meaningful_output),
        "grounded_claims": len(overlap),
        "faithfulness_score": round(coverage, 4),
        "ungrounded_examples": [],
        "method": "local_coverage_proxy",
    }


# ── Main evaluation ───────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="MAFD Layer 2 Faithfulness Evaluation")
    parser.add_argument("--scenarios", type=int, default=len(SCENARIOS),
                        help=f"Number of scenarios to run (default: {len(SCENARIOS)})")
    parser.add_argument("--local-only", action="store_true",
                        help="Skip LLM calls; use heuristic fallback + coverage proxy")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds between Azure calls (default: 1.0)")
    args = parser.parse_args()

    print("=" * 70)
    print("MAFD — Step 7: Layer 2 faithfulness evaluation")
    print("=" * 70)

    if not SOP_DIR.exists():
        print(f"[ERROR] SOP directory not found: {SOP_DIR}", file=sys.stderr)
        sys.exit(1)

    use_llm = _azure_configured() and not args.local_only
    if use_llm:
        print(f"\n[step7] Azure endpoint configured. Running LLM path.")
        print(f"        Endpoint  : {AZURE_ENDPOINT}")
        print(f"        Deployment: {AZURE_DEPLOYMENT}")
    else:
        if args.local_only:
            print("\n[step7] --local-only flag set. Running heuristic path.")
        else:
            print("\n[step7] Azure NOT configured. Running local heuristic fallback.")
            print("        Fill in .env with Azure credentials to run LLM faithfulness.")
            print("        Required keys:")
            print("          AZURE_OPENAI_ENDPOINT")
            print("          AZURE_OPENAI_API_KEY")
            print("          AZURE_OPENAI_DEPLOYMENT")

    # Load SOPs and build TF-IDF index
    sops = _load_sops()
    sop_ids    = list(sops.keys())
    sop_tokens = [_tokenize(sops[sid]["text"]) for sid in sop_ids]
    idf_map    = _idf(sop_tokens)
    print(f"\n[step7] SOPs loaded: {sop_ids}")

    scenarios = SCENARIOS[:args.scenarios]
    print(f"[step7] Running {len(scenarios)} scenarios...\n")

    all_results = []
    cp_list, cr_list, faith_list = [], [], []

    for i, sc in enumerate(scenarios, 1):
        print(f"  [{i:02d}/{len(scenarios)}] {sc['id']} ({sc['fault_type']}) ", end="", flush=True)

        # Retrieve
        retrieved = _retrieve(sc["query"], sops, sop_ids, sop_tokens, idf_map)
        gt = set(GROUND_TRUTH[sc["fault_type"]])
        ret_set = {r["id"] for r in retrieved}
        cp = len(ret_set & gt) / len(ret_set) if ret_set else 0.0
        cr = len(ret_set & gt) / len(gt) if gt else 0.0

        # Generate
        if use_llm:
            ticket = _generate_ticket_llm(sc, retrieved)
            if ticket is None:
                ticket = _generate_ticket_local(sc, retrieved)
                gen_method = "heuristic_fallback"
            else:
                gen_method = "llm"
            time.sleep(args.delay)
        else:
            ticket = _generate_ticket_local(sc, retrieved)
            gen_method = "heuristic"

        # Judge faithfulness
        if use_llm and gen_method == "llm":
            faith_result = _judge_faithfulness(ticket, sc, retrieved)
            faith_method = "llm_judge"
            time.sleep(args.delay)
        elif use_llm:
            # LLM run but generation failed after retry: don't mix the
            # coverage proxy into the judged mean.
            faith_result = None
        else:
            faith_result = _local_faithfulness(ticket, retrieved)
            faith_method = faith_result.get("method", "local_coverage_proxy")

        cp_list.append(cp)
        cr_list.append(cr)
        if faith_result is None:
            # Judge (or generation) failed: exclude from the mean rather than record 0.0.
            faith_result = {"total_claims": 0, "grounded_claims": 0,
                            "faithfulness_score": None, "ungrounded_examples": []}
            faith_method = "judge_failed" if gen_method == "llm" else "generation_failed"
            faith_score = None
            faith_str = "  n/a"
        else:
            faith_score = faith_result.get("faithfulness_score", 0.0)
            faith_list.append(faith_score)
            faith_str = f"{faith_score:.2f}"

        print(f"CP={cp:.2f}  CR={cr:.2f}  Faith={faith_str}  [{gen_method}/{faith_method}]")

        all_results.append({
            "scenario_id": sc["id"],
            "fault_type": sc["fault_type"],
            "feeder": sc["feeder"],
            "retrieved_sops": [r["id"] for r in retrieved],
            "ground_truth_sops": sorted(gt),
            "context_precision": round(cp, 4),
            "context_recall": round(cr, 4),
            "generation_method": gen_method,
            "faithfulness_method": faith_method,
            "faithfulness_score": None if faith_score is None else round(faith_score, 4),
            "total_claims": faith_result.get("total_claims", 0),
            "grounded_claims": faith_result.get("grounded_claims", 0),
            "ungrounded_examples": faith_result.get("ungrounded_examples", []),
            "generated_ticket": ticket,
        })

    # ── Aggregate results ──────────────────────────────────────────────────────
    mean_cp    = sum(cp_list) / len(cp_list)
    mean_cr    = sum(cr_list) / len(cr_list)
    mean_faith = sum(faith_list) / len(faith_list) if faith_list else 0.0
    halluc_rate = 1.0 - mean_faith
    n_judged = len(faith_list)

    print()
    print("=" * 70)
    print("RESULTS — Layer 2 Evaluation")
    print("=" * 70)
    print(f"{'Metric':<30} {'Score':>8}")
    print("-" * 40)
    print(f"{'Context Precision (retrieval)':<30} {mean_cp:>8.4f}")
    print(f"{'Context Recall (retrieval)':<30} {mean_cr:>8.4f}")
    print(f"{'Faithfulness Score':<30} {mean_faith:>8.4f}")
    print(f"{'Hallucination Rate':<30} {halluc_rate:>8.4f}")
    print()
    print(f"Scenarios evaluated : {len(scenarios)}")
    if n_judged != len(scenarios):
        print(f"Scenarios judged    : {n_judged}  ({len(scenarios) - n_judged} judge failures excluded)")
    print(f"Generation method   : {'LLM (Azure OpenAI)' if use_llm else 'Local heuristic fallback'}")
    print(f"Faithfulness method : {'LLM judge (Azure OpenAI)' if use_llm else 'Coverage proxy (no LLM)'}")

    if not use_llm:
        print()
        print("NOTE: Faithfulness score above is a vocabulary coverage proxy,")
        print("      not a true LLM faithfulness assessment. Configure Azure")
        print("      credentials in .env to obtain LLM-judged faithfulness.")

    # Per-fault-type breakdown
    print()
    print("By fault type:")
    by_type: dict[str, list] = defaultdict(list)
    for r in all_results:
        by_type[r["fault_type"]].append(r)
    for ft in sorted(by_type):
        rs = by_type[ft]
        cp_t = sum(r["context_precision"] for r in rs) / len(rs)
        cr_t = sum(r["context_recall"] for r in rs) / len(rs)
        judged = [r["faithfulness_score"] for r in rs if r["faithfulness_score"] is not None]
        f_t  = f"{sum(judged) / len(judged):.4f}" if judged else "   n/a"
        print(f"  {ft:<10}: CP={cp_t:.4f}  CR={cr_t:.4f}  Faithfulness={f_t}  n={len(rs)}")

    # Save full results to the next free numbered file so repeated runs
    # (the generator is stochastic) are kept side by side, never overwritten.
    run_number = 1
    while (RESULTS_DIR / f"faithfulness_evaluation_{run_number}.json").exists():
        run_number += 1
    out_path = RESULTS_DIR / f"faithfulness_evaluation_{run_number}.json"
    output = {
        "run_number": run_number,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "azure_endpoint": AZURE_ENDPOINT if use_llm else "not_configured",
        "azure_deployment": AZURE_DEPLOYMENT if use_llm else "not_used",
        "generation_mode": "llm" if use_llm else "local_heuristic",
        "faithfulness_mode": "llm_judge" if use_llm else "coverage_proxy",
        "n_scenarios": len(scenarios),
        "n_judged": n_judged,
        "aggregate": {
            "mean_context_precision": round(mean_cp, 4),
            "mean_context_recall": round(mean_cr, 4),
            "mean_faithfulness_score": round(mean_faith, 4),
            "hallucination_rate": round(halluc_rate, 4),
        },
        "scenarios": all_results,
    }
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\n[step7] Full results saved to {out_path.relative_to(REPO_ROOT)}")
    print("[step7] Done.")


if __name__ == "__main__":
    main()
