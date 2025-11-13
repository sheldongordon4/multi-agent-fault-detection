# scripts/load_to_sqlite.py

import sqlite3
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data" / "synthetic"
DB_PATH = ROOT_DIR / "data" / "synthetic_signals.db"



def load_csvs_to_sqlite():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Simple signals table. For MVP we just wipe and recreate on each run.
    cursor.execute("DROP TABLE IF EXISTS signals;")
    cursor.execute(
        """
        CREATE TABLE signals (
            timestamp TEXT,
            bus_id TEXT,
            voltage_kv REAL,
            current_a REAL,
            frequency_hz REAL,
            scenario TEXT,
            "27_undervoltage" INTEGER,
            "59_overvoltage" INTEGER,
            "50_overcurrent" INTEGER
        );
        """
    )

    # Simple scenarios metadata table
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

    for scenario, desc in descriptions.items():
        csv_path = DATA_DIR / f"{scenario}.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"Expected CSV not found: {csv_path}")

        df = pd.read_csv(csv_path)
        df.to_sql("signals", conn, if_exists="append", index=False)

        cursor.execute(
            "INSERT OR REPLACE INTO scenarios (name, description) VALUES (?, ?);",
            (scenario, desc),
        )

    conn.commit()
    conn.close()
    print(f"Loaded CSVs into SQLite at {DB_PATH}")


if __name__ == "__main__":
    load_csvs_to_sqlite()

