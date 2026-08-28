"""
analyze_testbed.py — DEEP analysis of the testbed fault CSVs (100% of rows, no sampling).

Loads each feeder CSV fully with pandas and reports summaries computed over the
COMPLETE data. It also saves the correlation/covariance/describe of the clean primary
file to data/generated/ as HUMAN-INSPECTION artifacts.

NOTE: generate_normal_data.py does NOT read these saved files — it recomputes its own
correlation from the calmest rows at runtime (a better-targeted estimate for normal
generation). These saved stats are for review only.

Run with the project venv:
    .venv/Scripts/python.exe scripts/analyze_testbed.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.load_testbed import (  # noqa: E402
    feature_columns,
)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 60)
pd.set_option("display.float_format", lambda v: f"{v:.4g}")

FAMILIES = [
    "min_Va_fault_pu",
    "max_Ia_fault",
    "max_I0_I1_fault",
    "max_I2_I1_fault",
    "mean_Vunb_fault",
    "recovery_Va_post",
]

FILES = {
    "013_mod_CLEAN": "data/new data/013 Bus Fault Analysis Batch (mod).csv",
    "013_orig_CORRUPT": "data/new data/013 Bus Fault Analysis Batch (orig).csv",
    "034_orig_CORRUPT": "data/new data/034 Bus Fault Analysis Batch (orig)/dataset_table.csv",
}


def banner(t: str) -> None:
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def detect_buses(feats):
    buses = []
    for c in feats:
        for fam in FAMILIES:
            p = fam + "_"
            if c.startswith(p):
                b = c[len(p):]
                if b not in buses:
                    buses.append(b)
    return buses


def analyze_file(tag: str, path: str):
    banner(f"FILE: {tag}  ->  {path}")
    df = pd.read_csv(ROOT / path)
    feats = feature_columns(df)
    buses = detect_buses(feats)
    Xnum = df[feats].apply(pd.to_numeric, errors="coerce")

    print(f"shape: {df.shape[0]} rows x {df.shape[1]} cols")
    print(f"feature cols: {len(feats)}  buses ({len(buses)}): {buses}")

    # --- corruption pattern: inf / nan ---
    is_inf = np.isinf(Xnum.to_numpy())
    is_nan = np.isnan(Xnum.to_numpy())
    finite_mask = np.isfinite(Xnum.to_numpy()).all(axis=1)
    n_bad = int((~finite_mask).sum())
    print(f"\n[corruption] rows with ANY inf/nan feature: {n_bad} "
          f"({n_bad/len(df):.1%})   clean rows: {int(finite_mask.sum())}")
    print(f"[corruption] total inf cells: {int(is_inf.sum())}   "
          f"total nan cells: {int(is_nan.sum())}")
    # which families carry inf vs nan?
    inf_by_fam = {f: 0 for f in FAMILIES}
    nan_by_fam = {f: 0 for f in FAMILIES}
    for j, col in enumerate(feats):
        fam = next((f for f in FAMILIES if col.startswith(f + "_")), None)
        if fam:
            inf_by_fam[fam] += int(is_inf[:, j].sum())
            nan_by_fam[fam] += int(is_nan[:, j].sum())
    print("[corruption] inf cells by family:", {k: v for k, v in inf_by_fam.items() if v})
    print("[corruption] nan cells by family:", {k: v for k, v in nan_by_fam.items() if v})

    # --- label distributions (100% of rows) ---
    for col in ["target_fault_type", "target_fault_category", "fault_subtype",
                "fault_category", "fault_phases"]:
        if col in df.columns:
            print(f"\n[value_counts] {col}:")
            print(df[col].value_counts(dropna=False).to_string())

    # --- per-fault-type bus-aggregated feature means (clean rows only) ---
    clean = df[finite_mask].copy()
    cleanX = Xnum[finite_mask]
    print(f"\n[clean subset] {len(clean)} rows used for distribution stats")

    # per-family aggregated describe (mean over buses per row, then describe)
    banner(f"{tag}: per-FAMILY describe (across all buses, clean rows)")
    fam_frame = {}
    for fam in FAMILIES:
        cols = [f"{fam}_{b}" for b in buses if f"{fam}_{b}" in feats]
        fam_frame[fam] = cleanX[cols].mean(axis=1)
    fam_df = pd.DataFrame(fam_frame)
    print(fam_df.describe().T.to_string())

    # --- per-bus describe of the two headline families ---
    for fam in ["min_Va_fault_pu", "max_Ia_fault", "max_I0_I1_fault"]:
        banner(f"{tag}: per-BUS describe — {fam} (clean rows)")
        cols = [f"{fam}_{b}" for b in buses if f"{fam}_{b}" in feats]
        print(cleanX[cols].describe().T.to_string())

    # --- per-fault-type breakdown: mean feature-family value by fault type ---
    banner(f"{tag}: per-FAULT-TYPE mean of each family (bus-averaged, clean rows)")
    ft = clean["target_fault_type"].reset_index(drop=True)
    agg = pd.DataFrame({fam: fam_df[fam].reset_index(drop=True) for fam in FAMILIES})
    agg["target_fault_type"] = ft.values
    print(agg.groupby("target_fault_type").mean().to_string())

    # --- suspect rows ---
    banner(f"{tag}: SUSPECT-ROW inspection")
    # extreme max_Ia
    ia_cols = [f"max_Ia_fault_{b}" for b in buses if f"max_Ia_fault_{b}" in feats]
    ia_max = Xnum[ia_cols].max(axis=1)
    finite_ia = ia_max[np.isfinite(ia_max)]
    if len(finite_ia):
        print(f"max_Ia over all buses: min={finite_ia.min():.4g} "
              f"median={finite_ia.median():.4g} p99={finite_ia.quantile(0.99):.4g} "
              f"max={finite_ia.max():.4g}")
        hi = finite_ia[finite_ia > 50000]
        print(f"rows with max_Ia > 50 kA: {len(hi)}")
        if len(hi):
            top = df.loc[hi.sort_values(ascending=False).index[:5],
                         ["scenario_name", "target_fault_type", "fault_category"]]
            top = top.assign(max_Ia=finite_ia.loc[top.index].round(0))
            print(top.to_string(index=False))
    # near-zero current bus (b675 on 13-bus)
    for b in buses:
        col = f"max_Ia_fault_{b}"
        if col in feats:
            v = Xnum[col]
            vf = v[np.isfinite(v)]
            if len(vf) and vf.median() < 5:  # essentially de-energized normally
                print(f"  near-zero-current bus {b}: median max_Ia={vf.median():.4g} "
                      f"(I0/I1 ratios here are small/small -> unstable)")
    # severe / de-energizing faults: min_Va near 0
    minva_cols = [f"min_Va_fault_pu_{b}" for b in buses if f"min_Va_fault_pu_{b}" in feats]
    deepest = Xnum[minva_cols].min(axis=1)
    df_sag = deepest[np.isfinite(deepest)]
    if len(df_sag):
        print(f"\ndeepest voltage sag (min over buses): "
              f"min={df_sag.min():.4g} median={df_sag.median():.4g}")
        print(f"rows that fully de-energize a bus (min_Va < 0.05): "
              f"{int((df_sag < 0.05).sum())}")

    return df, Xnum, feats, buses, finite_mask


def main():
    primary = None
    for tag, path in FILES.items():
        try:
            res = analyze_file(tag, path)
        except FileNotFoundError as e:
            banner(f"FILE: {tag} — MISSING")
            print(e)
            continue
        if tag == "013_mod_CLEAN":
            primary = res

    # --- correlation / covariance of the CLEAN primary (input for generator) ---
    if primary is not None:
        df, Xnum, feats, buses, finite_mask = primary
        cleanX = Xnum[finite_mask].reset_index(drop=True)
        banner("013_mod_CLEAN: feature CORRELATION matrix (abs summary)")
        corr = cleanX.corr()
        # Summarize: strongest off-diagonal correlations
        cc = corr.where(~np.eye(len(corr), dtype=bool))
        flat = cc.stack().sort_values(ascending=False)
        print("Top 15 strongest positive feature correlations:")
        seen = set()
        shown = 0
        for (a, b), v in flat.items():
            key = frozenset((a, b))
            if key in seen:
                continue
            seen.add(key)
            print(f"  {v:+.3f}  {a}  <->  {b}")
            shown += 1
            if shown >= 15:
                break
        print(f"\nmean |off-diagonal corr| = {cc.abs().stack().mean():.3f}")

        # Save artifacts for the generator
        outdir = ROOT / "data" / "generated"
        outdir.mkdir(parents=True, exist_ok=True)
        corr.to_csv(outdir / "stats_corr_013.csv")
        cleanX.cov().to_csv(outdir / "stats_cov_013.csv")
        cleanX.describe().T.to_csv(outdir / "stats_describe_013.csv")
        print(f"\n[saved] correlation/covariance/describe -> {outdir}")


if __name__ == "__main__":
    main()
