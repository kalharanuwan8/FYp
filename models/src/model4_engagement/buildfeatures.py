from __future__ import annotations
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

def _speed(xy: np.ndarray) -> np.ndarray:
    # xy shape (T,2), returns per-step speed length T-1, NaN-safe
    d = np.diff(xy, axis=0)
    sp = np.sqrt((d[:, 0] ** 2) + (d[:, 1] ** 2))
    return sp

def run(pose_csv: Path, out_csv: Path, window_sec: float = 2.0, stride_sec: float = 1.0):
    df = pd.read_csv(pose_csv)
    assert "t_sec" in df.columns, "pose.csv missing t_sec"

    t = df["t_sec"].to_numpy()
    t_max = float(np.nanmax(t))
    win = window_sec
    stride = stride_sec

    def colxy(name: str):
        return np.stack([df[f"{name}_x"].to_numpy(), df[f"{name}_y"].to_numpy()], axis=1)

    nose = colxy("nose")
    lw = colxy("l_wrist")
    rw = colxy("r_wrist")
    ls = colxy("l_shoulder")
    rs = colxy("r_shoulder")

    has_pose = df["has_pose"].to_numpy().astype(int)

    rows = []
    start = 0.0
    while start + win <= t_max:
        end = start + win
        idx = np.where((t >= start) & (t < end))[0]
        if len(idx) < 5:
            start += stride
            continue

        hp = has_pose[idx]
        pose_ratio = float(np.mean(hp))

        # Subset
        nose_w = nose[idx]
        lw_w = lw[idx]
        rw_w = rw[idx]
        ls_w = ls[idx]
        rs_w = rs[idx]

        shoulder_mid = np.nanmean(np.stack([ls_w, rs_w], axis=0), axis=0)  # (T,2)

        # Speeds (NaN-safe)
        lw_sp = _speed(lw_w)
        rw_sp = _speed(rw_w)

        # Distances: wrist to nose, wrist to shoulder mid (desk-zone proxy)
        lw_nose = np.sqrt(np.nansum((lw_w - nose_w) ** 2, axis=1))
        rw_nose = np.sqrt(np.nansum((rw_w - nose_w) ** 2, axis=1))

        lw_sh = np.sqrt(np.nansum((lw_w - shoulder_mid) ** 2, axis=1))
        rw_sh = np.sqrt(np.nansum((rw_w - shoulder_mid) ** 2, axis=1))

        # Stability (nose jitter)
        nose_jitter = float(np.nanmean(np.nanstd(nose_w, axis=0)))

        # "Hands below shoulders" ratio (writing/desk bias)
        # In normalized coords, larger y means lower in image.
        sh_y = shoulder_mid[:, 1]
        lw_below = float(np.nanmean(lw_w[:, 1] > sh_y))
        rw_below = float(np.nanmean(rw_w[:, 1] > sh_y))

        row = {
            "t_start": start,
            "t_end": end,
            "frames": int(len(idx)),
            "pose_ratio": pose_ratio,

            "lw_speed_mean": float(np.nanmean(lw_sp)),
            "lw_speed_std": float(np.nanstd(lw_sp)),
            "rw_speed_mean": float(np.nanmean(rw_sp)),
            "rw_speed_std": float(np.nanstd(rw_sp)),

            "lw_to_nose_mean": float(np.nanmean(lw_nose)),
            "rw_to_nose_mean": float(np.nanmean(rw_nose)),
            "lw_to_sh_mean": float(np.nanmean(lw_sh)),
            "rw_to_sh_mean": float(np.nanmean(rw_sh)),

            "nose_jitter": nose_jitter,
            "lw_below_sh_ratio": lw_below,
            "rw_below_sh_ratio": rw_below,
        }
        rows.append(row)
        start += stride

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"Saved features: {out_csv}  (windows={len(rows)})")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pose", default="data/processed/model4_engagement/pose.csv")
    ap.add_argument("--out", default="data/processed/model4_engagement/features.csv")
    ap.add_argument("--win", type=float, default=2.0)
    ap.add_argument("--stride", type=float, default=1.0)
    args = ap.parse_args()
    run(Path(args.pose), Path(args.out), window_sec=args.win, stride_sec=args.stride)
