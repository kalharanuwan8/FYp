# model4_engagement Inference script
from __future__ import annotations
from pathlib import Path
import argparse
import joblib
import numpy as np
import pandas as pd

def run(features_csv: Path, model_path: Path, out_csv: Path, video_id: str | None = None, append: bool = False):
    pack = joblib.load(model_path)
    model = pack["model"]
    cols = pack["feature_cols"]

    df = pd.read_csv(features_csv)
    X = df[cols].fillna(0.0).to_numpy().astype(np.float32)

    prob = model.predict_proba(X)[:, 1]
    out = df.copy()
    
    # Fusion compatibility
    if "t_start" in out.columns:
        out = out.rename(columns={"t_start": "window_start_sec"})
    
    # Ensure engagement_prob_mean exists
    out["engagement_prob_mean"] = prob
    
    # Add video_id
    if video_id:
        out["video_id"] = video_id
    elif "video_id" not in out.columns:
        out["video_id"] = features_csv.stem 

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    
    # Handle append
    write_header = not out_csv.exists() or not append
    write_mode = "a" if append else "w"
    out.to_csv(out_csv, index=False, mode=write_mode, header=write_header)
    
    print(f"Saved predictions: {out_csv} (append={append})")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="data/processed/model4_engagement/features.csv")
    ap.add_argument("--model", default="outputs/checkpoints/model4_engagement/model.pkl")
    ap.add_argument("--out", default="data/processed/model4_engagement/pred.csv")
    ap.add_argument("--video", type=str, help="Optional video path (used for video_id if not provided)")
    ap.add_argument("--video-id", type=str, help="Explicit video_id for fusion")
    ap.add_argument("--append", action="store_true", help="Append results to existing CSV")
    args = ap.parse_args()
    
    vid_id = args.video_id
    if not vid_id and args.video:
        vid_id = Path(args.video).stem

    run(Path(args.features), Path(args.model), Path(args.out), video_id=vid_id, append=args.append)

