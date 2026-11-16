"""
Why the detector called it a fault — per-feature attribution.

docs/System_Architecture.md calls this system explainable, but until now the
explanation was an LLM narrative written downstream of the verdict. The model
itself said only "anomaly, score 0.62". An operator cannot check that, and
neither can a protection engineer: the number carries no reference to any
quantity they measure.

This turns the verdict back into the measurements that produced it. Each feature
is scored against the NORMAL training distribution — the same rows the
IsolationForest learned from, so the comparison is against the model's own idea
of healthy rather than against a textbook value — and the largest departures are
reported with the bus and quantity they belong to:

    max_I0_I1_fault at b671 was 0.368 against a normal 0.003 (+121 sigma)

That sentence is defensible in a way generated prose is not. It is also the
cheapest form of explainability available here: no surrogate model, no SHAP, no
second inference pass, just the row and the baseline it was scored against.

WHAT IT IS NOT
--------------
Not a causal attribution and not a Shapley value. IsolationForest splits on
random features, so a large deviation is evidence, not proof, that this feature
drove the isolation. It answers "what is unusual about this event" rather than
"which input the model weighted most", and for an operator deciding where to
send a crew the first question is the useful one.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]

# The rows the detector trains on. Attribution has to compare against the same
# distribution the model did, or it explains a verdict some other model made.
NORMAL_TRAIN_CSV = ROOT_DIR / "data" / "generated" / "normal_train_013.csv"

# Human-readable names for the six feature families, so a ticket does not have
# to render a raw column name at an operator.
FAMILY_LABELS: dict[str, str] = {
    "min_Va_fault_pu": "phase-A voltage minimum",
    "max_Ia_fault": "phase-A current peak",
    "max_I0_I1_fault": "zero-sequence current ratio",
    "max_I2_I1_fault": "negative-sequence current ratio",
    "mean_Vunb_fault": "voltage unbalance",
    "recovery_Va_post": "post-fault voltage recovery",
}

# What an elevated value of each family means physically. This is the line that
# makes the attribution readable as protection engineering rather than as
# statistics.
FAMILY_MEANING: dict[str, str] = {
    "min_Va_fault_pu": "voltage collapsed at this bus",
    "max_Ia_fault": "fault current well above load",
    "max_I0_I1_fault": "current returning through ground",
    "max_I2_I1_fault": "phases carrying unequal current",
    "mean_Vunb_fault": "phase voltages pulled apart",
    "recovery_Va_post": "voltage did not return after clearing",
}

# A feature has to clear this many standard deviations before it is worth an
# operator's attention. Below it every row lists six mildly unusual numbers and
# the signal is lost in them.
MIN_SIGMA = 3.0

# Floor on the baseline spread. Several columns are near-constant in the normal
# set (b675 reports the same value in every healthy row), and dividing by their
# true standard deviation reports thousands of sigma for a rounding difference.
_MIN_STD = 1e-3

_baseline: dict[str, tuple[float, float]] | None = None
_baseline_tried = False


def _split_column(col: str) -> tuple[str, str]:
    """`max_I0_I1_fault_b671` -> ("max_I0_I1_fault", "b671")."""
    for family in FAMILY_LABELS:
        if col.startswith(f"{family}_"):
            return family, col[len(family) + 1 :]
    return col, ""


def load_baseline(csv_path: Path | str | None = None) -> dict[str, tuple[float, float]]:
    """Per-column (mean, std) over the normal training rows. Cached per process."""
    global _baseline, _baseline_tried
    if _baseline is not None:
        return _baseline
    if _baseline_tried and csv_path is None:
        return {}

    _baseline_tried = True
    path = Path(csv_path) if csv_path is not None else NORMAL_TRAIN_CSV
    if not path.exists():
        logger.warning("Attribution baseline missing at %s; verdicts go out unexplained.", path)
        return {}

    frame = pd.read_csv(path)
    stats: dict[str, tuple[float, float]] = {}
    for col in frame.columns:
        family, bus = _split_column(col)
        if family not in FAMILY_LABELS or not bus:
            continue
        series = pd.to_numeric(frame[col], errors="coerce").dropna()
        if series.empty:
            continue
        stats[col] = (float(series.mean()), max(float(series.std()), _MIN_STD))

    _baseline = stats
    return stats


def reset_baseline() -> None:
    """Drop the cached baseline. For tests, and after retraining."""
    global _baseline, _baseline_tried
    _baseline, _baseline_tried = None, False


def attribute(features: Any, top_k: int = 4, baseline: dict | None = None) -> list[dict[str, Any]]:
    """
    The features that put this event furthest outside normal, worst first.

    Returns [] rather than raising when the baseline is unavailable: attribution
    is enrichment, and a missing training CSV must not cost a ticket its verdict.
    """
    stats = baseline if baseline is not None else load_baseline()
    if not stats:
        return []

    if isinstance(features, pd.DataFrame):
        row = features.iloc[0]
    elif isinstance(features, pd.Series):
        row = features
    else:
        row = pd.Series(features)

    scored: list[dict[str, Any]] = []
    for col, (mean, std) in stats.items():
        if col not in row.index:
            continue
        value = pd.to_numeric(row[col], errors="coerce")
        if value is None or not math.isfinite(float(value)):
            continue
        value = float(value)
        sigma = (value - mean) / std
        if abs(sigma) < MIN_SIGMA:
            continue
        family, bus = _split_column(col)
        scored.append(
            {
                "feature": col,
                "bus": bus,
                "family": family,
                "label": FAMILY_LABELS.get(family, family),
                "meaning": FAMILY_MEANING.get(family, ""),
                "value": round(value, 4),
                "baseline": round(mean, 4),
                "sigma": round(sigma, 1),
                "direction": "above" if sigma > 0 else "below",
            }
        )

    scored.sort(key=lambda d: abs(d["sigma"]), reverse=True)

    # One line per physical quantity, at the bus where it departed most. Without
    # this the list is four rows about the same bus — true, since a bus whose
    # healthy spread is narrow dominates every ranking, but it tells an operator
    # one thing four times instead of four things once.
    best_per_family: dict[str, dict[str, Any]] = {}
    for item in scored:
        best_per_family.setdefault(item["family"], item)
    return sorted(best_per_family.values(), key=lambda d: abs(d["sigma"]), reverse=True)[:top_k]
