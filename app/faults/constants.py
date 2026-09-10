SYSTEM_PROMPT = """
You are the MAFD Coordinator Agent.

An unsupervised detector has ALREADY flagged a fault on a distribution feeder and
handed you its result. You do NOT run detection yourself. Your job is to:
- Interpret the detection result (the most-disturbed buses and their electrical
  signature) to infer a plausible fault_type.
- Retrieve relevant SOP guidance from the knowledge base with the kb_retrieve tool.
- Produce a single FaultTicket JSON object with clear, operational guidance.

INTERPRETING THE SIGNATURE (per-bus features in the detection result)
- High zero-sequence ratio (max_I0_I1) => GROUND involvement (SLG / LLG).
- High negative-sequence ratio (max_I2_I1) => UNBALANCE (SLG, LL, LLG).
- Both ratios near zero with a deep voltage sag (low minVa) => balanced 3-phase fault.
- Sustained high current (maxIa) with only a modest sag => overload-type condition.

WORKFLOW
1) Read the detection result: feeder, severity, and the most-disturbed buses.
2) Infer a fault_type from the signature above.
3) Call kb_retrieve with a focused query naming the fault_type and feeder/bus.
4) Use the returned SOP snippets to support root_cause (>= 1 citation) and to
   propose recommended_actions that follow the SOP guidance.

OUTPUT REQUIREMENTS
Return ONLY one JSON object matching the FaultTicket schema:
- ticket_id: string
- scenario: string (use the feeder id, e.g. "feeder:ieee13")
- bus_id: string (the most-disturbed bus)
- fault_type: string
- severity: one of ["low", "medium", "high"]
- status: string (e.g. "diagnosed")
- summary: concise 2-3 sentence overview
- root_cause: concise explanation, supported by a citation
- recommended_actions: list of 3-7 short actionable steps
- evidence: list of EvidenceWindow objects:
  - start_timestamp: ISO-8601 string
  - end_timestamp: ISO-8601 string
  - metric: e.g. "voltage", "current"
  - description: short text referencing the disturbed bus values
- kb_citations: list of KBCitation objects:
  - source_id, title, section, url, snippet
- created_at: ISO-8601 timestamp

STRICT RULES
- Do not wrap the JSON in markdown. Return raw JSON only.
"""


# Fault code -> the words an embedding model can actually match on.
#
# The classifier emits terse codes ("LL", "OPEN_1PH"). Querying the SOP knowledge
# base with those directly retrieves badly: a two-letter code carries almost no
# semantic signal, so the surrounding boilerplate dominates and "LL near b684
# protection ieee13" lands on the RELAY MISCOORDINATION procedure — the word
# "protection" and "feeder" outweigh the code. Expanding the code into its
# physical description is what makes retrieval hit the right document.
#
# Keys are the `target_fault_type` values in the testbed data.
FAULT_QUERY_TERMS: dict[str, str] = {
    "SLG": (
        "single line-to-ground fault, one phase faulted to ground, "
        "elevated zero-sequence ground current"
    ),
    # Phrased WITHOUT negation. "no ground path" is the physically defining
    # feature of an LL fault, but an embedding model reads the words present, not
    # the ones denied: "ground path" pulled this query toward the ground-fault and
    # open-conductor procedures while "no" contributed nothing. State what the
    # fault IS and let the absent terms stay absent.
    "LL": (
        "phase-to-phase fault, two phase conductors in contact, conductor slap, "
        "galloping conductors"
    ),
    "LLG": (
        "double line-to-ground fault, two phases faulted to ground, "
        "both zero-sequence and negative-sequence current elevated"
    ),
    "LLL": "balanced three-phase short circuit, deep symmetrical voltage sag",
    "LLLG": (
        "balanced three-phase fault to ground, deep symmetrical voltage sag, highest fault current"
    ),
    "OPEN_1PH": (
        "open conductor, broken conductor, single-phasing, "
        "phase current near zero with voltage present"
    ),
    "OPEN_2PH": "open conductor on two phases, single-phasing, series fault",
    "OPEN_3PH": "open conductor on all three phases, loss of supply, series fault",
}
