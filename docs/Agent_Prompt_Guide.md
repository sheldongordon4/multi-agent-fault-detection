# Agent Prompt Guide — MAFD

How the Coordinator agent is prompted. Authoritative design:
`docs/System_Architecture.md`; agent internals: `docs/Agent_Architecture.md`. The
live system prompt is `app/faults/constants.py` (`SYSTEM_PROMPT`) — treat that file
as the source of truth; this guide explains it.

## Coordinator role (detection-as-trigger)

Detection runs **upstream**. An unsupervised event detector (and, when trained, the
supervised classifier) has **already** flagged the fault and handed the Coordinator
its result. The Coordinator does **not** run detection. Its job:

1. Interpret the detection result — the most-disturbed buses and their electrical
   signature — to infer a plausible `fault_type`.
2. Retrieve relevant SOP guidance with the **`kb_retrieve`** tool.
3. Emit a single validated **`FaultTicket`** JSON object with operator-ready guidance.

## Interpreting the signature

- High zero-sequence ratio (`max_I0_I1`) ⇒ **ground** involvement (SLG / LLG).
- High negative-sequence ratio (`max_I2_I1`) ⇒ **unbalance** (SLG, LL, LLG).
- Both ratios near zero with a deep sag (low `minVa`) ⇒ **balanced 3-phase** fault.
- Sustained high current (`maxIa`) with only a modest sag ⇒ **overload-type** condition.

When detection attaches a supervised `classification` (`fault_type` /
`fault_category` / `location_km`), prefer it over the signature heuristic.

## Tool-calling rules

- **`kb_retrieve`** is the agent's **only** tool. Query it with a focused string
  naming the suspected fault type and the affected feeder/bus.
- There is **no** `detect_signal` tool — detection is the trigger, not a tool.
- **Do not fabricate citations.** Every `root_cause` should be backed by ≥ 1
  retrieved SOP; if retrieval returns nothing, say so rather than inventing one.
- Return **raw JSON only** (no markdown fences) matching the `FaultTicket` schema.

## Output schema

See `FaultTicket` in `app/faults/schemas.py`: `ticket_id`, `scenario`, `bus_id`,
`fault_type`, `severity` (`low|medium|high`), `status`, `summary`, `root_cause`,
`recommended_actions[]`, `evidence[]`, `kb_citations[]`, `created_at`. Severity and
status are coerced tolerantly (synonyms mapped; unknown values fall back to a safe
default) so a slightly-off LLM value doesn't reject the ticket.

## Offline fallback

If Azure is not configured, `run_fault_diagnosis` produces the ticket **without any
LLM call** — signature heuristics plus a direct `kb_retrieve`. This path is
intentional and must keep working; keep the two paths' output shape identical.
