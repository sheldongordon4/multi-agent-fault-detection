from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

# Directory + file for the demo signal CSV
SIGNALS_DIR = Path("artifacts/signals")
SIGNALS_FILE = SIGNALS_DIR / "demo_signals.csv"


def save_signals(
    timestamps: Iterable,
    values: Iterable[float],
    *,
    metric: str = "current",
    bus_id: str = "unknown_bus",
    scenario: str = "unknown_scenario",
) -> Path:
    """
    Save a timestamped signal window to artifacts/signals/demo_signals.csv

    Columns:
        timestamp (ISO8601 strings)
        metric (e.g., "current", "voltage")
        value (numeric)
        bus_id
        scenario

    The Streamlit UI will read and plot this CSV as the "real" flagged signal.
    """
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "timestamp": list(timestamps),
            "metric": metric,
            "value": list(values),
            "bus_id": bus_id,
            "scenario": scenario,
        }
    )

    df.to_csv(SIGNALS_FILE, index=False)
    return SIGNALS_FILE
