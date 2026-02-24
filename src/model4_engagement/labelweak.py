from __future__ import annotations
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

def run(features_csv: Path, out_csv: Path):
    df = pd.read_csv(features_csv)

    # Weak supervision rules (tune later)
    # - needs pose visible
    # - hands mostly below shoulders (desk zone)
    # - some wrist motion, but not crazy jitter
    pose_ok = df["pose_ratio"] > 0.7

    below_ok = (df["lw_below_sh_ratio"] > 0.6) | (df["rw_below_sh_ratio"] > 0.6)

    # motion threshold: small but non-zero
    motion = (df["lw_speed_mean"].fillna(0) + df["rw_speed_mean"].fillna(0)) / 2.0
    motion_ok = motion > 0.002  # normalized units; adjust if needed

    # stability gate: not too jittery
    stable_ok = df["nose_jitter"] < 0.01

    active = (pose_ok & below_ok & motion_ok & stable_ok).astype(int)

    out = df.copy()
    out["active_work"] = active

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)

    print(f"Saved weak labels: {out_csv}")
    print("Label counts:\n", out["active_work"].value_counts())

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="data/processed/model3_activity/features.csv")
    ap.add_argument("--out", default="data/processed/model3_activity/labeled.csv")
    args = ap.parse_args()
    run(Path(args.features), Path(args.out))
