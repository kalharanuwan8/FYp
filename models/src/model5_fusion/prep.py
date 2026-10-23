"""
Fusion dataset preparation (replaces prepare.py).

1. Loads gaze, pose, engagement window CSVs from each model
2. Merges on (video_id, window_start_sec)
3. Applies weak labeling based on video identity + feature sanity checks
4. Splits with forced class balance in validation set

Outputs:
  data/processed/model5_fusion/train.csv
  data/processed/model5_fusion/val.csv
  data/processed/model5_fusion/test.csv
  data/processed/model5_fusion/meta.json
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd


# ── Config ────────────────────────────────────────────────────────────
OUT_DIR = Path("data/processed/model5_fusion")

GAZE_FILES = [
    Path("data/processed/model1_gaze/window_preds_distracted.csv"),
    Path("data/processed/model1_gaze/window_preds_forced.csv"),
    Path("data/processed/model1_gaze/window_preds_natural.csv"),
]
POSE_FILES = [
    Path("data/processed/model2_pose/window_pose_distracted.csv"),
    Path("data/processed/model2_pose/window_pose_forced.csv"),
    Path("data/processed/model2_pose/window_pose_natural.csv"),
]
ENG_FILES = [
    Path("data/processed/model4_engagement/pred_distracted.csv"),
    Path("data/processed/model4_engagement/preds_forced.csv"),
    Path("data/processed/model4_engagement/preds_natural.csv"),
]

# Label mapping
DISTRACTED_VIDS = {"distracted"}
FOCUSED_VIDS    = {"natural", "forced", "focused"}

# Stratified split ratios (window-level, NOT video-level)
TRAIN_RATIO = 0.70
VAL_RATIO   = 0.15
TEST_RATIO  = 0.15
RANDOM_STATE = 42


# ── Weak labeling ────────────────────────────────────────────────────
def weak_label(r):
    """
    Hybrid weak-labeling: video identity + feature sanity check.
    Returns 1 = distracted, 0 = not distracted, -1 = ambiguous.
    """
    vid       = r["video_id"]
    gaze_away = r["gaze_away_ratio"]
    yaw       = abs(r["yaw_mean"])
    pitch     = abs(r["pitch_mean"])

    if vid in DISTRACTED_VIDS:
        if gaze_away > 0.20 or yaw > 10 or pitch > 10:
            return 1
        return -1   # surprisingly focused window in "distracted" video

    if vid in FOCUSED_VIDS:
        if yaw < 40 and pitch < 40:
            return 0
        return -1   # surprisingly distracted window in "focused" video

    return -1       # unknown video


# ── Main ─────────────────────────────────────────────────────────────
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- 1. Load & validate -------------------------------------------------
    for f in GAZE_FILES + POSE_FILES + ENG_FILES:
        if not f.exists():
            raise FileNotFoundError(f"Missing: {f}")

    gaze = pd.concat([pd.read_csv(f) for f in GAZE_FILES], ignore_index=True)
    pose = pd.concat([pd.read_csv(f) for f in POSE_FILES], ignore_index=True)
    eng  = pd.concat([pd.read_csv(f) for f in ENG_FILES],  ignore_index=True)

    # Normalize engagement column name
    if "engagement_prob_mean" not in eng.columns:
        if "active_work_prob" in eng.columns:
            eng = eng.rename(columns={"active_work_prob": "engagement_prob_mean"})
        elif "prob" in eng.columns:
            eng = eng.rename(columns={"prob": "engagement_prob_mean"})
        else:
            raise ValueError("Engagement CSV missing engagement_prob_mean / prob / active_work_prob")

    for c in ["video_id", "window_start_sec", "p_center", "p_left", "p_right", "p_down"]:
        if c not in gaze.columns:
            raise ValueError(f"Model1 gaze CSV missing: {c}")
    for c in ["video_id", "window_start_sec", "yaw_mean", "pitch_mean", "roll_mean"]:
        if c not in pose.columns:
            raise ValueError(f"Model2 pose CSV missing: {c}")
    for c in ["video_id", "window_start_sec", "engagement_prob_mean"]:
        if c not in eng.columns:
            raise ValueError(f"Model4 engagement CSV missing: {c}")

    # --- 2. Align & merge ---------------------------------------------------
    for frame in [gaze, pose, eng]:
        frame["window_start_sec"] = frame["window_start_sec"].round(0).astype(int)

    gaze = gaze.groupby(["video_id", "window_start_sec"], as_index=False).first()
    pose = pose.groupby(["video_id", "window_start_sec"], as_index=False).first()
    eng  = eng.groupby(["video_id", "window_start_sec"],  as_index=False).first()

    df = gaze.merge(pose, on=["video_id", "window_start_sec"], how="inner")
    print(f"  After gaze+pose merge: {len(df)} rows, videos: {list(df['video_id'].unique())}")
    df = df.merge(eng,  on=["video_id", "window_start_sec"], how="inner")
    print(f"  After +engagement merge: {len(df)} rows")

    # --- 3. Feature engineering ---------------------------------------------
    df["p_center_mean"] = df["p_center"]
    df["p_left_mean"]   = df["p_left"]
    df["p_right_mean"]  = df["p_right"]
    df["p_down_mean"]   = df["p_down"]

    s = df["p_center_mean"] + df["p_left_mean"] + df["p_right_mean"] + df["p_down_mean"] + 1e-8
    df["gaze_away_ratio"] = (df["p_left_mean"] + df["p_right_mean"] + df["p_down_mean"]) / s

    # --- 4. Weak labels -----------------------------------------------------
    df["y"] = df.apply(weak_label, axis=1)
    print(f"  Label distribution before filtering: {df['y'].value_counts().to_dict()}")
    df = df[df["y"] != -1].copy()
    print(f"  After dropping ambiguous (-1): {len(df)} rows")

    feat_cols = [
        "p_center_mean", "p_left_mean", "p_right_mean", "p_down_mean",
        "gaze_away_ratio",
        "yaw_mean", "pitch_mean", "roll_mean",
        "yaw_std",  "pitch_std",  "roll_std",
        "engagement_prob_mean",
    ]
    feat_cols = [c for c in feat_cols if c in df.columns]
    keep_cols = feat_cols + ["y", "video_id", "window_start_sec"]
    df = df[keep_cols].copy()

    # --- 5. Stratified window-level split -----------------------------------
    #   Shuffle, then split each class proportionally so every split has both.
    from sklearn.model_selection import train_test_split

    # First split: train vs (val + test)
    val_test_ratio = VAL_RATIO + TEST_RATIO
    df_train, df_valtest = train_test_split(
        df, test_size=val_test_ratio, stratify=df["y"], random_state=RANDOM_STATE
    )

    # Second split: val vs test (from the val+test pool)
    relative_test = TEST_RATIO / val_test_ratio
    df_val, df_test = train_test_split(
        df_valtest, test_size=relative_test, stratify=df_valtest["y"], random_state=RANDOM_STATE
    )

    # Reset indices
    df_train = df_train.reset_index(drop=True)
    df_val   = df_val.reset_index(drop=True)
    df_test  = df_test.reset_index(drop=True)

    # --- 6. Save ------------------------------------------------------------
    df_train.to_csv(OUT_DIR / "train.csv", index=False)
    df_val.to_csv(OUT_DIR / "val.csv",     index=False)
    df_test.to_csv(OUT_DIR / "test.csv",   index=False)
    (OUT_DIR / "meta.json").write_text(json.dumps({"features": feat_cols}, indent=2))

    print(f"\nSaved fusion dataset to {OUT_DIR}/")
    print(f"  train: {len(df_train)} rows | class: {df_train['y'].value_counts().to_dict()}")
    print(f"  val:   {len(df_val)} rows   | class: {df_val['y'].value_counts().to_dict()}")
    print(f"  test:  {len(df_test)} rows  | class: {df_test['y'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
