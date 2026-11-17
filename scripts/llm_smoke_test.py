"""
llm_smoke_test.py - a *strictly bounded* live check of the coordinator's LLM endpoint.

Why this exists
---------------
Running the full app (Kafka -> detector -> coordinator graph -> LLM) to confirm the
endpoint works would fire an unbounded number of chat completions - which eats a
paid credit or burns through a free tier's daily quota. This script instead makes
AT MOST 2 calls to the endpoint, then stops - hard.

It is provider-agnostic, because the coordinator is: it reads whatever
OpenAI-compatible endpoint is configured (Google AI Studio by default).

Guardrails baked in:
  * A process-wide counter caps real endpoint calls at MAX_ENDPOINT_CALLS (2).
    The 3rd attempt raises before any network I/O.
  * max_retries=0            -> a failure never silently becomes extra calls.
  * max_tokens=16            -> each completion is tiny (minimal token spend).
  * No graph, no tool loop   -> each test is a single .invoke(), one round-trip.
  * Requires --confirm       -> you can't trigger paid calls by accident.

It reads the endpoint/key from your .env via the app's own FaultsConfig, so the
secrets are never printed and the var names always match the app.

Usage:
    python -m scripts.llm_smoke_test --confirm
"""

from __future__ import annotations

import argparse
import json
import sys

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from backend.faults.config import settings
from backend.utils import message_text

# ---- hard cap on billable calls -------------------------------------------------
MAX_ENDPOINT_CALLS = 3

# Why this is not 16 any more: reasoning models (Gemini 3.x, o-series) spend
# output tokens on internal thinking BEFORE emitting any visible content. A
# 16-token ceiling is consumed entirely by thinking, so the call succeeds, bills
# you, and returns an EMPTY string with finish_reason="length" - which reads as
# "the endpoint is broken" when nothing is broken at all. 512 is still tiny, and
# the point of the cap was always the CALL count, not the token count.
MAX_TOKENS = 512

_calls_made = 0


def _guarded_invoke(llm, messages):
    """Invoke the model, but refuse to ever exceed MAX_ENDPOINT_CALLS."""
    global _calls_made
    if _calls_made >= MAX_ENDPOINT_CALLS:
        raise RuntimeError(
            f"Refusing to call the endpoint: cap of {MAX_ENDPOINT_CALLS} already reached."
        )
    _calls_made += 1
    print(f"  -> endpoint call {_calls_made}/{MAX_ENDPOINT_CALLS} ...")
    resp = llm.invoke(messages)
    _report(resp)
    return resp


def _report(resp) -> None:
    """
    Print why a call produced what it did.

    An empty reply is the failure mode most likely to be misread, because the
    request itself succeeded. finish_reason and the token split say whether the
    model was truncated, filtered, or genuinely silent - so print them always,
    not only on failure.
    """
    meta = getattr(resp, "response_metadata", {}) or {}
    usage = getattr(resp, "usage_metadata", {}) or {}
    finish = meta.get("finish_reason", "?")
    bits = [f"finish_reason={finish!r}"]
    if usage:
        bits.append(f"in={usage.get('input_tokens')}")
        bits.append(f"out={usage.get('output_tokens')}")
        details = usage.get("output_token_details") or {}
        if details.get("reasoning"):
            bits.append(f"reasoning={details['reasoning']}")
    print("     " + "  ".join(bits))
    if finish == "length":
        print("     ^ truncated: raise MAX_TOKENS (thinking tokens ate the budget)")


def _make_llm():
    """
    The coordinator's own client factory, with the cost knobs turned down.

    It calls backend.faults.agent.build_chat_model rather than constructing a client
    here. That is the point: this script previously built its OWN ChatOpenAI,
    so when the coordinator moved to the native Google client the smoke test
    silently kept testing the old path and reported on a client the app no
    longer uses. A test that builds its own subject is not testing the app.

    max_retries=0 matters for the call cap - retries happen INSIDE one invoke(),
    so they would bypass the counter in _guarded_invoke.
    """
    from backend.faults.agent import build_chat_model

    return build_chat_model(max_retries=0, max_tokens=MAX_TOKENS, rate_limiter=None)


def test_1_connectivity(llm) -> bool:
    """Call 1/2: bare auth + reachability check."""
    print("[test 1] connectivity / auth")
    resp = _guarded_invoke(
        llm,
        [
            SystemMessage(content="Reply with exactly one word."),
            HumanMessage(content="Say: pong"),
        ],
    )
    text = message_text(resp.content).strip()
    print(f"  reply: {text!r}")
    ok = bool(text)
    print(f"  result: {'PASS' if ok else 'FAIL (empty reply)'}")
    return ok


def test_2_tool_round_trip(llm) -> bool:
    """
    Calls 2 and 3: a REAL two-turn tool loop - request, execute, send back.

    WHY THIS IS NOT ONE ROUND-TRIP ANY MORE
    ---------------------------------------
    It used to be, and it passed against a configuration that could not work.
    A single .invoke() only proves the endpoint ACCEPTS a `tools` payload. The
    failure that actually matters happens on the SECOND request, when the tool
    result is sent back alongside the assistant message that asked for it:

        400 INVALID_ARGUMENT - Function call is missing a thought_signature in
        functionCall parts ... position 2

    Gemini 3.x attaches reasoning state to a function call and wants it echoed
    back; the OpenAI-compat format has nowhere to put it. A one-turn test never
    reaches that, so it reported PASS while the coordinator was unusable.

    This is the shape of the ReAct loop in backend/faults/agent.py, minus LangGraph:
    ask -> tool_calls -> run the tool locally -> hand the result back -> answer.
    """
    print("[test 2] tool ROUND TRIP (two turns - this is the one that matters)")
    from backend.faults.tools import kb_retrieve

    llm_with_tools = llm.bind_tools([kb_retrieve])
    messages = [
        SystemMessage(
            content=(
                "You answer using the kb_retrieve tool. Call it first, then "
                "reply with the source_id you found. Be terse."
            )
        ),
        HumanMessage(
            content="Which SOP covers a single line-to-ground fault on a distribution feeder?"
        ),
    ]

    # --- turn 1: the model should ask for the tool ---
    first = _guarded_invoke(llm_with_tools, messages)
    tool_calls = getattr(first, "tool_calls", []) or []
    print(f"  turn 1: tool_calls requested = {len(tool_calls)}")
    if not tool_calls:
        print("  result: FAIL (model never called the tool - nothing to round-trip)")
        return False

    # --- run the tool locally, exactly as ToolNode would ---
    messages.append(first)
    for call in tool_calls:
        try:
            result = kb_retrieve.invoke(call["args"])
        except Exception as exc:  # noqa: BLE001 - the KB is not what we're testing
            result = f"tool error: {exc}"
        messages.append(
            ToolMessage(
                content=json.dumps(result, default=str)[:2000],
                tool_call_id=call["id"],
            )
        )
    print(f"  ran {len(tool_calls)} tool call(s) locally, sending results back ...")

    # --- turn 2: THE request that fails when signatures are dropped ---
    second = _guarded_invoke(llm_with_tools, messages)
    text = message_text(second.content).strip()
    print(f"  turn 2 reply: {text[:120]!r}")
    ok = bool(text)
    print(f"  result: {'PASS' if ok else 'FAIL (empty answer after tool result)'}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=f"Required. Authorize up to {MAX_ENDPOINT_CALLS} real endpoint calls.",
    )
    args = parser.parse_args()

    if not settings.llm_configured:
        print(
            "No LLM endpoint configured (endpoint/key/model missing or placeholder).\n"
            "Set LLM_API_KEY (and LLM_ENDPOINT / LLM_MODEL) in .env, then re-run. No endpoint call was made.",
            file=sys.stderr,
        )
        return 2

    if not args.confirm:
        print(
            f"This makes UP TO {MAX_ENDPOINT_CALLS} live endpoint calls (max_tokens={MAX_TOKENS} each).\n"
            "Re-run with --confirm to proceed. No endpoint call was made.",
            file=sys.stderr,
        )
        return 1

    llm = _make_llm()
    results = [
        test_1_connectivity(llm),
        test_2_tool_round_trip(llm),
    ]

    print("-" * 48)
    print(f"endpoint calls made: {_calls_made}/{MAX_ENDPOINT_CALLS}")
    passed = sum(results)
    print(f"tests passed: {passed}/{len(results)}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
