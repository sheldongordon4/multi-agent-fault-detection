# scripts/generate_synthetic_data.py

from pathlib import Path
import os
from typing import Literal

import numpy as np
import pandas as pd

# Project root is one level up from scripts/
ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data" / "synthetic"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# Three buses / feeders for the MVP
BUS_IDS = ["bus_1", "bus_2", "bus_3"]

# Relay flags we care about
RELAY_FLAGS = ["27_undervoltage", "59_overvoltage", "50_overcurrent"]


def generate_time_index(duration_minutes: int = 60, freq: str = "S") -> pd.DatetimeIndex:
    """Generate a simple time index starting at t0 for a given duration."""
    periods = duration_minutes * 60
    return pd.date_range("2025-01-01 00:00:00", periods=periods, freq=freq)


def _base_signal(
    timestamps: pd.DatetimeIndex,
    bus_id: str,
    scenario: Literal["normal", "overload_trip", "miscoordination", "theft_overload"],
) -> pd.DataFrame:
    """
    Generate base SCADA signals + relay flags for one bus and scenario.

    Schema:
      timestamp, bus_id, voltage_kv, current_a, frequency_hz,
      27_undervoltage, 59_overvoltage, 50_overcurrent, scenario
    """
    n = len(timestamps)

    # Normal operating ranges (rough, simple)
    base_voltage_kv = 13.8
    base_current_a = 100.0
    base_freq_hz = 60.0

    # Start from normal with small noise
    voltage = np.random.normal(loc=base_voltage_kv, scale=0.1, size=n)
    current = np.random.normal(loc=base_current_a, scale=5.0, size=n)
    frequency = np.random.normal(loc=base_freq_hz, scale=0.02, size=n)

    # Relay flags initialised to 0
    flags = {flag: np.zeros(n, dtype=int) for flag in RELAY_FLAGS}

    # Scenario-specific perturbations
    # Define a "fault window" in the middle of the trace
    fault_start = int(n * 0.4)
    fault_end = int(n * 0.6)

    if scenario == "normal":
        # Nothing special, just normal noise
        pass

    elif scenario == "overload_trip":
        # Current ramps up a lot, overcurrent flag set in the window
        current[fault_start:fault_end] += 80.0  # strong overload
        flags["50_overcurrent"][fault_start:fault_end] = 1

    elif scenario == "miscoordination":
        # Mild overload plus some voltage sag, but relay flags behave inconsistently
        current[fault_start:fault_end] += 50.0
        voltage[fault_start:fault_end] -= 0.7
        # Overcurrent sometimes delayed or missing
        flags["50_overcurrent"][fault_start + int(0.1 * (fault_end - fault_start)):fault_end] = 1
        # Maybe an undervoltage flag appears too early
        flags["27_undervoltage"][fault_start - int(0.05 * (fault_end - fault_start)):fault_start] = 1

    elif scenario == "theft_overload":
        # Gradual current increase over a long interval, with subtle voltage sag
        slope = np.linspace(0, 60.0, fault_end - fault_start)
        current[fault_start:fault_end] += slope
        voltage[fault_start:fault_end] -= 0.4
        # Overcurrent trips very late or intermittently
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
            "scenario": scenario,
        }
    )

    # Add relay flags
    for flag in RELAY_FLAGS:
        df[flag] = flags[flag]

    return df


def generate_scenario_dataset(
    scenario: Literal["normal", "overload_trip", "miscoordination", "theft_overload"],
    duration_minutes: int = 60,
) -> pd.DataFrame:
    """Generate a multi bus dataset for a given scenario."""
    timestamps = generate_time_index(duration_minutes=duration_minutes)
    dfs = []

    for bus in BUS_IDS:
        dfs.append(_base_signal(timestamps, bus, scenario))

    all_data = pd.concat(dfs, ignore_index=True)
    return all_data


def main() -> None:
    scenarios = ["normal", "overload_trip", "miscoordination", "theft_overload"]

    for scenario in scenarios:
        df = generate_scenario_dataset(scenario, duration_minutes=60)
        out_path = DATA_DIR / f"{scenario}.csv"
        df.to_csv(out_path, index=False)
        print(f"Wrote {scenario} dataset to {out_path} (rows={len(df)})")


if __name__ == "__main__":
    main()

