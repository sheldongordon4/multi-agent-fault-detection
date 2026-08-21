"""
Dedicated executors for the two kinds of off-loop work.

Everything used to go through `asyncio.to_thread`, which shares ONE default
ThreadPoolExecutor sized `min(32, cpu_count + 4)` — 12 workers on the 8-CPU dev
container. That pool was doing two incompatible jobs at once:

  * **librdkafka polling.** Every consumer group parks a worker inside a blocking
    `consumer.poll(timeout)` essentially all the time — an idle poll holds one for
    a full second. With five groups that is 5 of 12 workers permanently occupied
    doing nothing.
  * **CPU-bound ML.** IsolationForest scoring, RandomForest classification and the
    coordinator's KB/embedding work.

When events flowed, the ML work grabbed workers on top of the five already parked,
and the streaming consumer's own `poll`/`commit` calls queued behind them. It
stopped draining `raw.signals`, so the live signal chart froze while tickets and
toasts kept arriving (those ride a single short HTTP refetch, which survives a
starved pool; a 20 Hz SSE feed does not).

Splitting the pools fixes the starvation; running ML in *processes* additionally
removes GIL contention, which was delaying the event loop even when a worker was
free. See docs/System_Architecture.md §16 and AGENTS.md TODO.
"""

import asyncio
import functools
import logging
import os
from collections.abc import Callable
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# One worker per consumer group with headroom for the commit/close calls that
# interleave with polling. Sized generously: these threads are almost always
# parked in a blocking C call, so they cost a thread, not a CPU.
_KAFKA_MAX_WORKERS = 16

# Processes, not threads: sklearn scoring is CPU-bound Python, so in a thread it
# holds the GIL and stalls the asyncio loop (and therefore the SSE writers) even
# when the thread pool has capacity. Kept small — each worker loads its own copy
# of the models.
_ML_MAX_WORKERS = min(2, os.cpu_count() or 1)

_kafka_pool: ThreadPoolExecutor | None = None
_ml_pool: ProcessPoolExecutor | None = None


def kafka_pool() -> ThreadPoolExecutor:
    global _kafka_pool
    if _kafka_pool is None:
        _kafka_pool = ThreadPoolExecutor(
            max_workers=_KAFKA_MAX_WORKERS, thread_name_prefix="kafka"
        )
    return _kafka_pool


def ml_pool() -> ProcessPoolExecutor | None:
    """
    The ML process pool, or None if it can't be created.

    Process pools fail in some sandboxes/platforms; callers fall back to a thread
    so detection keeps working (slower, but not broken).
    """
    global _ml_pool
    if _ml_pool is None:
        try:
            _ml_pool = ProcessPoolExecutor(max_workers=_ML_MAX_WORKERS)
        except Exception:
            logger.exception("Could not start ML process pool; falling back to threads")
            return None
    return _ml_pool


async def _run_on(executor: Executor, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, functools.partial(fn, *args, **kwargs))


async def run_kafka(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a blocking librdkafka call off the event loop, on the Kafka pool."""
    return await _run_on(kafka_pool(), fn, *args, **kwargs)


async def run_ml(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Run CPU-bound model work in a separate process.

    `fn` must be importable at module level and its arguments picklable — that's
    why the callables live in app/ml/scoring.py and take plain dicts, loading the
    models lazily inside each worker process instead of shipping them per call.
    """
    pool = ml_pool()
    if pool is None:
        return await asyncio.to_thread(functools.partial(fn, *args, **kwargs))
    try:
        return await _run_on(pool, fn, *args, **kwargs)
    except Exception:
        # A dead pool (worker crash) would otherwise fail every later event.
        logger.exception("ML process pool call failed; retrying on a thread")
        _reset_ml_pool()
        return await asyncio.to_thread(functools.partial(fn, *args, **kwargs))


async def prewarm_ml() -> None:
    """
    Spawn the ML worker processes and load the models inside each, up front.

    Measured cold: ~3.8s for the first call (process spawn + model load) versus
    ~0.03s once warm. Without this that delay lands on the first real fault event.
    One task per worker, run concurrently so each picks up a different process.
    """
    from app.ml.scoring import warm_models

    pool = ml_pool()
    if pool is None:
        return
    try:
        await asyncio.gather(
            *(_run_on(pool, warm_models) for _ in range(_ML_MAX_WORKERS))
        )
        logger.info("ML process pool warm (%d workers)", _ML_MAX_WORKERS)
    except Exception:
        logger.exception("ML pool pre-warm failed; workers will load on demand")


def _reset_ml_pool() -> None:
    global _ml_pool
    pool, _ml_pool = _ml_pool, None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def shutdown_executors() -> None:
    """Called from the FastAPI lifespan so workers don't outlive the app."""
    global _kafka_pool, _ml_pool
    if _kafka_pool is not None:
        # Don't wait: the threads are parked in blocking polls that end when the
        # consumers close.
        _kafka_pool.shutdown(wait=False, cancel_futures=True)
        _kafka_pool = None
    if _ml_pool is not None:
        _ml_pool.shutdown(wait=True, cancel_futures=True)
        _ml_pool = None
