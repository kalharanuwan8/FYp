import pandas as pd
from pathlib import Path

def normalize(path):
    path = Path(path)
    if not path.exists():
        print(f"Skipping: {path} (not found)")
        return
    
    df = pd.read_csv(path)
    # force video_id to file stem if missing or contains .mp4
    stem = path.stem
    # If the stem is 'window_preds_forced' or similar, we might want to extract just 'forced'
    # But usually video_id is things like 'natural', 'forced', 'distracted'
    # Based on the user's logic, they replace .mp4
    
    if "video_id" not in df.columns:
        df["video_id"] = stem
    
    df["video_id"] = df["video_id"].astype(str).str.replace(".mp4", "", regex=False)
    
    # Fix: if video_id contains the model prefix, clean it up for fusion
    # e.g., 'window_preds_forced' -> 'forced'
    for prefix in ["window_preds_", "window_pose_", "preds_", "pred_"]:
        df["video_id"] = df["video_id"].str.replace(prefix, "", regex=False)

    if "window_start_sec" in df.columns:
        df["window_start_sec"] = pd.to_numeric(df["window_start_sec"], errors="coerce").round(3)
    
    df.to_csv(path, index=False)
    print(f"Fixed: {path} | video_id uniques: {df['video_id'].unique().tolist()}")

if __name__ == "__main__":
    files = [
        "data/processed/model1_gaze/window_preds_distracted.csv",
        "data/processed/model1_gaze/window_preds_forced.csv",
        "data/processed/model1_gaze/window_preds_natural.csv",
        "data/processed/model2_pose/window_pose_distracted.csv",
        "data/processed/model2_pose/window_pose_forced.csv",
        "data/processed/model2_pose/window_pose_natural.csv",
        "data/processed/model4_engagement/pred_distracted.csv",
        "data/processed/model4_engagement/preds_forced.csv",
        "data/processed/model4_engagement/preds_natural.csv",
    ]
    for f in files:
        normalize(f)
