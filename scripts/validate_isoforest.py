"""
validate_isoforest.py — acceptance test for the IsolationForest fault trigger.

Trains the IsolationForest on a NORMAL-only CSV, then scores a MIXED validation CSV
(generated normal + injected real faults) and reports how well it separates them:

  - recall on faults  : of the real faults, how many did it flag?      (want HIGH)
  - false-alarm rate  : of the normal rows, how many did it wrongly flag? (want LOW)
  - precision         : of everything it flagged, how many were real faults?

The target_fault_type label is used ONLY for scoring (NO_FAULT vs a fault type);
the model itself never sees labels — it's unsupervised.

Usage:
    python scripts/validate_isoforest.py \
        --train data/generated/normal_train_013.csv \
        --val   data/generated/validation_013.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sklearn.ensemble import IsolationForest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.load_testbed import load_testbed  # noqa: E402

NO_FAULT_LABEL = "NO_FAULT"


def main():
    p = argparse.ArgumentParser(description="Validate the IsolationForest trigger.")
    p.add_argument("--train", required=True, help="NORMAL-only training CSV")
    p.add_argument("--val", required=True, help="Mixed (normal+faults) validation CSV")
    p.add_argument("--contamination", type=float, default=0.01,
                   help="Expected anomaly fraction in the NORMAL training data. "
                        "Tuned to 0.01. HELD-OUT results (val generated with a seed "
                        "different from train, so val-normal is NOT in training): "
                        "13-bus recall 0.941 / false-alarm 0.007; "
                        "34-bus recall 1.000 / false-alarm 0.007. Raise toward 0.05 "
                        "for higher recall on borderline OPEN faults at some precision cost.")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    #  Train on normal only (labels ignored — unsupervised).
    X_train, _, feats_train = load_testbed(args.train, target_col="target_fault_type")
    model = IsolationForest(
        n_estimators=200, contamination=args.contamination, random_state=args.seed
    )
    model.fit(X_train.values)

    #Score the mixed validation set.
    X_val, y_val, feats_val = load_testbed(args.val, target_col="target_fault_type")
    if feats_train != feats_val:
        raise SystemExit(
            "Feature columns differ between train and val (different feeder?)."
        )

    pred = model.predict(X_val.values)          # -1 = anomaly, 1 = normal
    flagged = pred == -1
    is_fault = (y_val != NO_FAULT_LABEL).to_numpy()

    n_fault = int(is_fault.sum())
    n_normal = int((~is_fault).sum())
    tp = int((flagged & is_fault).sum())        # faults correctly flagged
    fp = int((flagged & ~is_fault).sum())       # normals wrongly flagged
    fn = n_fault - tp
    tn = n_normal - fp

    recall = tp / n_fault if n_fault else float("nan")
    false_alarm = fp / n_normal if n_normal else float("nan")
    precision = tp / (tp + fp) if (tp + fp) else float("nan")

    print("\n=== IsolationForest validation ===")
    print(f"train normal rows : {len(X_train)}")
    print(f"val rows          : {len(X_val)}  ({n_fault} faults, {n_normal} normal)")
    print(f"contamination     : {args.contamination}")
    print("\n                  flagged   not-flagged")
    print(f"  real fault    {tp:9d}{fn:14d}")
    print(f"  real normal   {fp:9d}{tn:14d}")
    print(f"\nrecall on faults  : {recall:.3f}   (want HIGH — caught the faults)")
    print(f"false-alarm rate  : {false_alarm:.3f}   (want LOW — few normal flagged)")
    print(f"precision         : {precision:.3f}")


if __name__ == "__main__":
    main()
