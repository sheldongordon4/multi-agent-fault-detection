"""
Process-wide cost guardrail for the coordinator's Azure LLM usage.

Every real chat-completion call the coordinator makes must first `spend()` one
unit of budget. Once `settings.LLM_MAX_ENDPOINT_CALLS` units are spent, `spend()`
raises `LLMBudgetExceeded` and the service permanently falls back to the local
(no-LLM) ticket builder. This is a hard stop, independent of the per-model retry
and rate-limit settings, so a runaway ReAct loop or a long-lived worker can never
quietly drain your Azure credit.

The counter is per-process and thread-safe. It is deliberately NOT resettable from
normal app code (only tests reset it) so the ceiling can't be bumped at runtime.
"""

import threading

from app.faults.config import settings


class LLMBudgetExceeded(RuntimeError):
    """Raised when an LLM call would exceed the process endpoint-call budget."""


_lock = threading.Lock()
_calls_made = 0


def calls_made() -> int:
    """How many endpoint calls have been spent so far this process."""
    return _calls_made


def remaining() -> int:
    """Endpoint calls still allowed before the budget is exhausted."""
    return max(0, settings.LLM_MAX_ENDPOINT_CALLS - _calls_made)


def exhausted() -> bool:
    """True once no endpoint calls remain (or the budget is zero)."""
    return remaining() <= 0


def spend() -> int:
    """
    Reserve one endpoint call and return the new running total.

    Raises LLMBudgetExceeded (before any network I/O) if the budget is spent.
    """
    global _calls_made
    with _lock:
        if _calls_made >= settings.LLM_MAX_ENDPOINT_CALLS:
            raise LLMBudgetExceeded(
                f"LLM endpoint-call budget of {settings.LLM_MAX_ENDPOINT_CALLS} exhausted; "
                "coordinator is now using the local fallback."
            )
        _calls_made += 1
        return _calls_made


def _reset_for_tests() -> None:
    """Reset the counter. Intended for tests only."""
    global _calls_made
    with _lock:
        _calls_made = 0
