"""
load_testbed.py — load ONE testbed fault CSV into (X, y) for supervised training.

A testbed CSV describes one feeder. Each row is one simulated fault. The columns
fall into three groups:

  - metadata   (scenario_name, fault_*, Zf_*)          -> NOT model inputs
  - targets    (target_fault_type/category/location)   -> what we predict (y)
  - features   (everything else = the per-bus measurements) -> model inputs (X)

Feature columns are detected automatically (everything that is not metadata or a
target), so the same loader works for the 13-bus or 34-bus file without edits.
This is "Path A": one model per feeder, so we load one file at a time.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Union

import numpy as np
import pandas as pd

# Scenario-description columns
METADATA_COLUMNS: List[str] = [
    "scenario_name",
    "fault_category",
    "fault_subtype",
    "fault_phases",
    "fault_branch_id",
    "fault_pos_pu",
    "fault_bus_id",
    "fault_location_km",
    "Zf_real_ohm",
    "Zf_imag_ohm",
]

# Columns we could predict
TARGET_COLUMNS: List[str] = [
    "target_fault_type",
    "target_fault_category",
    "target_location_km",
]


def feature_columns(df: pd.DataFrame) -> List[str]:
    """Feature columns = every column that is not metadata and not a target."""
    non_features = set(METADATA_COLUMNS) | set(TARGET_COLUMNS)
    return [c for c in df.columns if c not in non_features]


def load_testbed(
    csv_path: Union[str, Path],
    target_col: str = "target_fault_type",
    drop_nonfinite: bool = True,
) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    """
    Load a testbed CSV into (X, y, feature_cols).

    Args:
        csv_path:     path to one testbed fault CSV (one feeder).
        target_col:   which target column to predict (default: fault type).
        drop_nonfinite: drop rows containing inf/nan features (the de-energized
                        testbed artifact). True is safe for training.

    Returns:
        X            DataFrame of per-bus feature columns (model inputs)
        y            Series of labels from `target_col`
        feature_cols list of the column names in X (so training & inference agree)
    """
    df = pd.read_csv(csv_path)

    feats = feature_columns(df)
    # Coerce features to numeric so inf/nan checks are reliable.
    X = df[feats].apply(pd.to_numeric, errors="coerce")
    y = df[target_col].copy()

    if drop_nonfinite:
        finite_mask = np.isfinite(X.to_numpy()).all(axis=1)
        dropped = int((~finite_mask).sum())
        if dropped:
            print(
                f"[load_testbed] dropping {dropped} rows with inf/nan features "
                f"({dropped / len(df):.1%} of {len(df)})"
            )
        X, y = (
            X[finite_mask].reset_index(drop=True),
            y[finite_mask].reset_index(drop=True),
        )

    print(
        f"[load_testbed] {len(X)} rows, {len(feats)} feature columns, "
        f"target='{target_col}' with {y.nunique()} classes"
    )
    return X, y, feats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inspect a testbed CSV as (X, y).")
    parser.add_argument("--csv", required=True, help="Path to a testbed fault CSV")
    parser.add_argument("--target", default="target_fault_type")
    args = parser.parse_args()

    X, y, feats = load_testbed(args.csv, target_col=args.target)
    print("\nfeature columns:", feats[:3], "...", feats[-1])
    print("\nclass balance:")
    print(y.value_counts())
