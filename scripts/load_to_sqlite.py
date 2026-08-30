"""Load the synthetic signal CSVs into the local SQLite demo database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data" / "synthetic"
DB_PATH = DATA_DIR / "synthetic_signals.db"


def load_csvs_to_sqlite() -> None:
    """Create the demo SQLite tables and load all synthetic CSVs into them."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS signals;")
    cursor.execute(
        """
        CREATE TABLE signals (
            timestamp TEXT,
            bus_id TEXT,
            voltage_kv REAL,
            current_a REAL,
            frequency_hz REAL,
            temperature_c REAL,
            scenario TEXT,
            "27_undervoltage" INTEGER,
            "59_overvoltage" INTEGER,
            "50_overcurrent" INTEGER
        );
        """
    )

    cursor.execute("DROP TABLE IF EXISTS scenarios;")
    cursor.execute(
        """
        CREATE TABLE scenarios (
            name TEXT PRIMARY KEY,
            description TEXT
        );
        """
    )

    descriptions = {
        "normal": "Baseline normal operation for all buses.",
        "overload_trip": "Clear overload with relay overcurrent trip.",
        "miscoordination": "Protection miscoordination between devices.",
        "theft_overload": "Theft driven overload with delayed tripping.",
    }

    for scenario, description in descriptions.items():
        csv_path = DATA_DIR / f"{scenario}.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"Expected CSV not found: {csv_path}")

        df = pd.read_csv(csv_path)
        df.to_sql("signals", conn, if_exists="append", index=False)

        cursor.execute(
            "INSERT OR REPLACE INTO scenarios (name, description) VALUES (?, ?);",
            (scenario, description),
        )

    conn.commit()
    conn.close()
    print(f"Loaded CSVs into SQLite at {DB_PATH}")


if __name__ == "__main__":
    load_csvs_to_sqlite()

