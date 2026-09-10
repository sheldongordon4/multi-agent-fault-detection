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
import sys

from langchain_core.messages import HumanMessage, SystemMessage

from app.faults.config import settings

# ---- hard cap on billable calls -------------------------------------------------
MAX_ENDPOINT_CALLS = 2

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
    """Same client the coordinator builds, but retry-free and token-capped."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url=settings.LLM_ENDPOINT,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        max_retries=0,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_tokens=MAX_TOKENS,
    )


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
    text = (resp.content or "").strip()
    print(f"  reply: {text!r}")
    ok = bool(text)
    print(f"  result: {'PASS' if ok else 'FAIL (empty reply)'}")
    return ok


def test_2_tool_binding(llm) -> bool:
    """Call 2/2: the coordinator binds a tool, so confirm tool-calling works too.

    This is the test that matters when switching providers: plenty of endpoints
    speak the OpenAI chat protocol but handle `tools` differently, and the ReAct
    loop is useless without it.

    Single .invoke() - we do NOT run the ReAct loop, so this stays one round-trip.
    """
    print("[test 2] tool-binding sanity (single round-trip, no tool loop)")
    from app.faults.tools import kb_retrieve

    llm_with_tools = llm.bind_tools([kb_retrieve])
    resp = _guarded_invoke(
        llm_with_tools,
        [
            SystemMessage(content="You may call kb_retrieve if useful. Be terse."),
            HumanMessage(content="Reply OK."),
        ],
    )
    text = (resp.content or "").strip()
    n_tool_calls = len(getattr(resp, "tool_calls", []) or [])
    print(f"  reply: {text!r}  (tool_calls requested: {n_tool_calls})")
    # A valid structured response (content or a tool call) means the endpoint
    # supports the coordinator's usage.
    ok = bool(text) or n_tool_calls > 0
    print(f"  result: {'PASS' if ok else 'FAIL'}")
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
        test_2_tool_binding(llm),
    ]

    print("-" * 48)
    print(f"endpoint calls made: {_calls_made}/{MAX_ENDPOINT_CALLS}")
    passed = sum(results)
    print(f"tests passed: {passed}/{len(results)}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
