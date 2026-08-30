"""
reproduce_steps_1_4.py
======================
Run the first four paper reproduction steps as a single grouped workflow.

This retains the original behavior while making the purpose, order, and failure
handling easier to read and maintain.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"

STEPS = [
    ("reproduce_step1_generate_data", "Step 1 — Dataset generation"),
    ("reproduce_step2_detection", "Step 2 — Detection results  (Table 1, cross-feeder, escalation)"),
    ("reproduce_step3_classification", "Step 3 — Classification results  (Tables 2, 3, location)"),
    ("reproduce_step4_latency", "Step 4 — Pipeline latency  (Table 4)"),
]


def _run_step(module_name: str, description: str) -> bool:
    """Execute a reproduction step module and return whether it succeeded."""
    script_path = SCRIPT_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load step module: {module_name}")

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        module.main()
        return True
    except SystemExit as exc:
        print(f"\n[reproduce_steps_1_4] {description} exited with code {exc.code}", file=sys.stderr)
        return False
    except Exception as exc:  # pragma: no cover - diagnostic output path
        print(f"\n[reproduce_steps_1_4] {description} raised: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


def main() -> None:
    print("=" * 70)
    print("MAFD — Reproduction for Steps 1–4")
    print("=" * 70)
    print()

    overall_start = time.perf_counter()
    results: list[tuple[str, bool, float]] = []

    for module_name, description in STEPS:
        print(f"\n{'=' * 70}")
        print(f"  {description}")
        print(f"{'=' * 70}")
        start = time.perf_counter()
        success = _run_step(module_name, description)
        elapsed = time.perf_counter() - start
        results.append((description, success, elapsed))

    total = time.perf_counter() - overall_start

    print("\n\n" + "=" * 70)
    print("REPRODUCTION SUMMARY")
    print("=" * 70)
    for desc, ok, elapsed in results:
        status = "OK" if ok else "FAILED"
        print(f"  [{status:^6}]  {desc:<52}  {elapsed:5.1f}s")
    print(f"\n  Total wall-clock time: {total:.1f}s")

    failed = [desc for desc, ok, _ in results if not ok]
    if failed:
        print(f"\n[WARNING] {len(failed)} step(s) failed:")
        for desc in failed:
            print(f"          {desc}")
        sys.exit(1)

    print("\n  All steps completed successfully.")


if __name__ == "__main__":
    main()
