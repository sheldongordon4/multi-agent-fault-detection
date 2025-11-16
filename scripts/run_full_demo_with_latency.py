# scripts/run_full_demo_with_latency.py
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCIDENTS_DIR = ROOT / "artifacts" / "incidents"


def run_cmd(cmd: str) -> None:
    """
    Run a shell command in the project root, show stdout/stderr,
    and raise if it fails.
    """
    proc = subprocess.run(
        cmd,
        shell=True,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        # This will show the "Wrote ticket to ..." line, etc.
        print(proc.stdout.strip())

    if proc.stderr:
        print(f"[stderr from '{cmd}']\n{proc.stderr}")

    proc.check_returncode()


def main():
    scenario = "overload_trip"
    bus_id = "bus_1"
    ticket_id = f"LOCAL-{scenario}-{bus_id}"
    ticket_path = INCIDENTS_DIR / f"{ticket_id}.json"

    # Optional: clear old ticket file if it exists
    if ticket_path.exists():
        ticket_path.unlink()

    # 1) Measure full pipeline latency: detection → ticket writer
    t0 = time.perf_counter()

    pipeline_cmd = (
        f"python scripts/run_detection_demo.py "
        f"--scenario {scenario} --bus_id {bus_id} "
        f"| python scripts/make_ticket_from_demo.py"
    )
    run_cmd(pipeline_cmd)

    t1 = time.perf_counter()
    latency_sec = t1 - t0

    # 2) Load the ticket JSON from artifacts/incidents
    if not ticket_path.exists():
        raise FileNotFoundError(
            f"Expected ticket file not found at: {ticket_path}. "
            "Check that make_ticket_from_demo.py writes to this path."
        )

    with ticket_path.open("r", encoding="utf-8") as f:
        ticket = json.load(f)

    # 3) Wrap and print a clean demo object
    wrapped = {
        "latencySec": latency_sec,
        "ticketFile": str(ticket_path.relative_to(ROOT)),
        "ticket": ticket,
    }

    print("\n=== Final Demo Output (Goal 5) ===")
    print(json.dumps(wrapped, indent=2))
    print(f"\n*** Total detection→diagnosis latency: {latency_sec:.2f} s ***")


if __name__ == "__main__":
    main()
