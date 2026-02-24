from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

OUT_DIR = Path("data/processed/model5_fusion")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# EDIT THESE FILENAMES TO MATCH YOUR 3 VIDEOS
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

# Manual split (best with only 3 videos)
TRAIN_VIDS = {"natural", "forced"}      # stems
VAL_VIDS   = {"natural"}               # optional (overlaps train; still ok for demo)
TEST_VIDS  = {"distracted"}

# Label mapping: which videos are "distracted" vs "not-distracted"
DISTRACTED_VIDS = {"distracted"}
FOCUSED_VIDS    = {"natural", "forced"}

def weak_label(r):
    """
    Hybrid weak-labeling: use video identity as the primary signal,
    with feature-based heuristics as a secondary filter.
    Returns 1 = distracted, 0 = not distracted, -1 = ambiguous.
    """
    vid = r["video_id"]
    gaze_away = r["gaze_away_ratio"]
    yaw = abs(r["yaw_mean"])
    pitch = abs(r["pitch_mean"])
    eng = r["engagement_prob_mean"]

    # Primary: trust the video label
    if vid in DISTRACTED_VIDS:
        # Feature sanity-check: only label as distracted if features are
        # at least somewhat consistent (gaze not perfectly centered)
        if gaze_away > 0.20 or yaw > 10 or pitch > 10:
            return 1
        return -1  # surprisingly focused window in "distracted" video

    if vid in FOCUSED_VIDS:
        # Feature sanity-check: only label as focused if not wildly off
        if yaw < 40 and pitch < 40:
            return 0
        return -1  # surprisingly distracted window in "focused" video

    return -1  # unknown video

def run():
    for f in GAZE_FILES + POSE_FILES + ENG_FILES:
        if not f.exists():
            raise FileNotFoundError(f"Missing: {f}")

    gaze = pd.concat([pd.read_csv(f) for f in GAZE_FILES], ignore_index=True)
    pose = pd.concat([pd.read_csv(f) for f in POSE_FILES], ignore_index=True)
    eng  = pd.concat([pd.read_csv(f) for f in ENG_FILES], ignore_index=True)

    # Normalize engagement column name
    if "engagement_prob_mean" not in eng.columns:
        if "active_work_prob" in eng.columns:
            eng = eng.rename(columns={"active_work_prob": "engagement_prob_mean"})
        elif "prob" in eng.columns:
            eng = eng.rename(columns={"prob": "engagement_prob_mean"})
        else:
            raise ValueError("Engagement CSV missing engagement_prob_mean/prob/active_work_prob")

    # Expect required columns
    for c in ["video_id", "window_start_sec", "p_center", "p_left", "p_right", "p_down"]:
        if c not in gaze.columns:
            raise ValueError(f"Model1 gaze CSV missing: {c}")

    for c in ["video_id", "window_start_sec", "yaw_mean", "pitch_mean", "roll_mean"]:
        if c not in pose.columns:
            raise ValueError(f"Model2 pose CSV missing: {c}")

    for c in ["video_id", "window_start_sec", "engagement_prob_mean"]:
        if c not in eng.columns:
            raise ValueError(f"Model4 engagement CSV missing: {c}")

    # Round window_start_sec to nearest integer so gaze (4.999) aligns
    # with engagement (5.0) — the models use slightly different strides
    for frame in [gaze, pose, eng]:
        frame["window_start_sec"] = frame["window_start_sec"].round(0).astype(int)

    # De-duplicate after rounding (keep first occurrence per group)
    gaze = gaze.groupby(["video_id", "window_start_sec"], as_index=False).first()
    pose = pose.groupby(["video_id", "window_start_sec"], as_index=False).first()
    eng  = eng.groupby(["video_id", "window_start_sec"],  as_index=False).first()

    # Merge
    df = gaze.merge(pose, on=["video_id", "window_start_sec"], how="inner")
    print(f"  After gaze+pose merge: {len(df)} rows, video_ids: {list(df['video_id'].unique())}")
    df = df.merge(eng,  on=["video_id", "window_start_sec"], how="inner")
    print(f"  After +engagement merge: {len(df)} rows")

    # Feature engineering
    df["p_center_mean"] = df["p_center"]
    df["p_left_mean"]   = df["p_left"]
    df["p_right_mean"]  = df["p_right"]
    df["p_down_mean"]   = df["p_down"]

    s = df["p_center_mean"] + df["p_left_mean"] + df["p_right_mean"] + df["p_down_mean"] + 1e-8
    df["gaze_away_ratio"] = (df["p_left_mean"] + df["p_right_mean"] + df["p_down_mean"]) / s

    # Weak labels
    df["y"] = df.apply(weak_label, axis=1)
    print(f"  Label distribution before filtering: {df['y'].value_counts().to_dict()}")
    df = df[df["y"] != -1].copy()
    print(f"  After dropping ambiguous (-1): {len(df)} rows")

    feat_cols = [
        "p_center_mean","p_left_mean","p_right_mean","p_down_mean",
        "gaze_away_ratio",
        "yaw_mean","pitch_mean","roll_mean",
        "yaw_std","pitch_std","roll_std",
        "engagement_prob_mean",
    ]
    # if std cols missing, drop them
    feat_cols = [c for c in feat_cols if c in df.columns]

    # Split
    df_train = df[df["video_id"].isin(TRAIN_VIDS)].copy()
    df_val   = df[df["video_id"].isin(VAL_VIDS)].copy()
    df_test  = df[df["video_id"].isin(TEST_VIDS)].copy()

    df_train[feat_cols + ["y","video_id","window_start_sec"]].to_csv(OUT_DIR/"train.csv", index=False)
    df_val[feat_cols + ["y","video_id","window_start_sec"]].to_csv(OUT_DIR/"val.csv", index=False)
    df_test[feat_cols + ["y","video_id","window_start_sec"]].to_csv(OUT_DIR/"test.csv", index=False)

    (OUT_DIR/"meta.json").write_text(json.dumps({"features": feat_cols}, indent=2))

    print("Saved fusion dataset:")
    print(" train:", len(df_train), "rows | class:", df_train["y"].value_counts().to_dict())
    print(" val:  ", len(df_val),   "rows | class:", df_val["y"].value_counts().to_dict() if len(df_val) else {})
    print(" test: ", len(df_test),  "rows | class:", df_test["y"].value_counts().to_dict())

if __name__ == "__main__":
    run()
