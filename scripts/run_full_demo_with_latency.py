"""Run the local detection→ticket demo and report end-to-end latency."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCIDENTS_DIR = ROOT / "artifacts" / "incidents"


def run_cmd(cmd: str) -> None:
    """Run a shell command from the project root and surface stdout/stderr."""
    proc = subprocess.run(
        cmd,
        shell=True,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(f"[stderr from '{cmd}']\n{proc.stderr}")

    proc.check_returncode()


def ticket_path_for(scenario: str, bus_id: str) -> Path:
    """Return the ticket file produced by the demo ticket helper."""
    ticket_id = f"LOCAL-{scenario}-{bus_id}"
    return INCIDENTS_DIR / f"{ticket_id}.json"


def main() -> None:
    scenario = "overload_trip"
    bus_id = "bus_1"
    ticket_path = ticket_path_for(scenario, bus_id)

    if ticket_path.exists():
        ticket_path.unlink()

    t0 = time.perf_counter()
    pipeline_cmd = (
        f"python scripts/run_detection_demo.py "
        f"--scenario {scenario} --bus_id {bus_id} "
        f"| python scripts/make_ticket_from_demo.py"
    )
    run_cmd(pipeline_cmd)
    latency_sec = time.perf_counter() - t0

    if not ticket_path.exists():
        raise FileNotFoundError(
            f"Expected ticket file not found at: {ticket_path}. "
            "Check that make_ticket_from_demo.py writes to this path."
        )

    with ticket_path.open("r", encoding="utf-8") as f:
        ticket = json.load(f)

    wrapped = {
        "latencySec": latency_sec,
        "ticketFile": str(ticket_path.relative_to(ROOT)),
        "ticket": ticket,
    }

    print("\n=== Final Demo Output ===")
    print(json.dumps(wrapped, indent=2))
    print(f"\n*** Total detection→diagnosis latency: {latency_sec:.2f} s ***")


if __name__ == "__main__":
    main()
