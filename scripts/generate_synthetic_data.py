"""Generate simple synthetic feeder SCADA datasets for the demo and signal pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data" / "synthetic"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BUS_IDS = ["bus_1", "bus_2", "bus_3"]
RELAY_FLAGS = ["27_undervoltage", "59_overvoltage", "50_overcurrent"]
ScenarioName = Literal["normal", "overload_trip", "miscoordination", "theft_overload"]


def generate_time_index(duration_minutes: int = 60, freq: str = "s") -> pd.DatetimeIndex:
    """Generate a simple time index for a given scenario duration."""
    periods = duration_minutes * 60
    return pd.date_range("2025-01-01 00:00:00", periods=periods, freq=freq)


def _base_signal(timestamps: pd.DatetimeIndex, bus_id: str, scenario: ScenarioName) -> pd.DataFrame:
    """Generate a base SCADA signal trace plus relay flags for one bus and scenario."""
    n = len(timestamps)

    base_voltage_kv = 13.8
    base_current_a = 100.0
    base_freq_hz = 60.0
    base_temp_c = 45.0

    voltage = np.random.normal(loc=base_voltage_kv, scale=0.1, size=n)
    current = np.random.normal(loc=base_current_a, scale=5.0, size=n)
    frequency = np.random.normal(loc=base_freq_hz, scale=0.02, size=n)
    temperature_c = np.random.normal(loc=base_temp_c, scale=1.0, size=n)
    flags = {flag: np.zeros(n, dtype=int) for flag in RELAY_FLAGS}

    fault_start = int(n * 0.4)
    fault_end = int(n * 0.6)

    if scenario == "normal":
        pass
    elif scenario == "overload_trip":
        current[fault_start:fault_end] += 80.0
        temperature_c[fault_start:fault_end] += 15.0
        flags["50_overcurrent"][fault_start:fault_end] = 1
    elif scenario == "miscoordination":
        current[fault_start:fault_end] += 50.0
        voltage[fault_start:fault_end] -= 0.7
        temperature_c[fault_start:fault_end] += 8.0
        flags["50_overcurrent"][fault_start + int(0.1 * (fault_end - fault_start)):fault_end] = 1
        flags["27_undervoltage"][fault_start - int(0.05 * (fault_end - fault_start)):fault_start] = 1
    elif scenario == "theft_overload":
        slope = np.linspace(0, 60.0, fault_end - fault_start)
        current[fault_start:fault_end] += slope
        temperature_c[fault_start:fault_end] += np.linspace(0, 12.0, fault_end - fault_start)
        late_start = fault_start + int(0.6 * (fault_end - fault_start))
        flags["50_overcurrent"][late_start:fault_end] = 1
    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "bus_id": bus_id,
            "voltage_kv": voltage,
            "current_a": current,
            "frequency_hz": frequency,
            "temperature_c": temperature_c,
            "scenario": scenario,
        }
    )

    for flag in RELAY_FLAGS:
        df[flag] = flags[flag]

    return df


def generate_scenario_dataset(
    scenario: ScenarioName,
    duration_minutes: int = 60,
) -> pd.DataFrame:
    """Generate a multi-bus dataset for a single scenario."""
    timestamps = generate_time_index(duration_minutes=duration_minutes)
    frames = [_base_signal(timestamps, bus_id, scenario) for bus_id in BUS_IDS]
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    scenarios: list[ScenarioName] = [
        "normal",
        "overload_trip",
        "miscoordination",
        "theft_overload",
    ]

    for scenario in scenarios:
        df = generate_scenario_dataset(scenario, duration_minutes=60)
        out_path = DATA_DIR / f"{scenario}.csv"
        df.to_csv(out_path, index=False)
        print(f"Wrote {scenario} dataset to {out_path} (rows={len(df)})")


if __name__ == "__main__":
    main()
