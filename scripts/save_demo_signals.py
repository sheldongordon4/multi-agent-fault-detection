# scripts/save_demo_signals.py (example pattern)

from __future__ import annotations
from pathlib import Path
import pandas as pd

OUT_PATH = Path("artifacts/signals/demo_signals.csv")

def save_signals(timestamps, values, bus_id: str, scenario: str, metric: str = "current") -> None:
    df = pd.DataFrame(
        {
            "timestamp": timestamps,   # list/array of ISO strings or datetime
            "metric": metric,
            "value": values,          # numeric list/array
            "bus_id": bus_id,
            "scenario": scenario,
        }
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)

