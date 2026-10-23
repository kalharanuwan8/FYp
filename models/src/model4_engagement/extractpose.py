from __future__ import annotations
from pathlib import Path
import argparse
import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm
import mediapipe as mp

# For MediaPipe 0.10.32, use the tasks API
BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# Pose landmark indices (MediaPipe Pose 33-point model)
KEYPOINTS = {
    "nose": 0,
    "l_shoulder": 11,
    "r_shoulder": 12,
    "l_elbow": 13,
    "r_elbow": 14,
    "l_wrist": 15,
    "r_wrist": 16,
}

def run(video_path: Path, out_csv: Path, max_frames: int = -1):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    rows = []

    # Try to find the model file
    # Download from: https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task
    model_path = Path(__file__).parent / "pose_landmarker_heavy.task"
    
    if not model_path.exists():
        # Try alternative lightweight model
        model_path = Path(__file__).parent / "pose_landmarker_lite.task"
    
    if not model_path.exists():
        print(f"Warning: Model file not found at {model_path}")
        print("Please download a pose landmarker model from:")
        print("https://developers.google.com/mediapipe/solutions/vision/pose_landmarker#models")
        print("and place it in: {}".format(Path(__file__).parent))
        raise FileNotFoundError(f"Pose landmarker model not found: {model_path}")

    # Create pose landmarker options for VIDEO mode
    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        running_mode=VisionRunningMode.VIDEO,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5
    )

    detector = PoseLandmarker.create_from_options(options)

    n = 0
    pbar = tqdm(total=(total if total > 0 else None), desc="Extracting pose")
    
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            n += 1
            if max_frames > 0 and n > max_frames:
                break

            # Convert BGR to RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Create MediaPipe Image
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            
            # Process for video
            timestamp_ms = int((n - 1) / fps * 1000)
            result = detector.detect_for_video(mp_image, timestamp_ms)

            t_sec = (n - 1) / fps
            row = {"frame": n, "t_sec": t_sec, "has_pose": 0}

            if result.pose_landmarks and len(result.pose_landmarks) > 0:
                row["has_pose"] = 1
                lms = result.pose_landmarks[0]  # First detected pose
                for name, idx in KEYPOINTS.items():
                    if idx < len(lms):
                        lm = lms[idx]
                        row[f"{name}_x"] = lm.x
                        row[f"{name}_y"] = lm.y
                        row[f"{name}_vis"] = lm.visibility if hasattr(lm, 'visibility') else 1.0
                    else:
                        row[f"{name}_x"] = np.nan
                        row[f"{name}_y"] = np.nan
                        row[f"{name}_vis"] = np.nan
            else:
                # fill NaNs
                for name in KEYPOINTS:
                    row[f"{name}_x"] = np.nan
                    row[f"{name}_y"] = np.nan
                    row[f"{name}_vis"] = np.nan

            rows.append(row)
            pbar.update(1)
    finally:
        pbar.close()
        cap.release()
        detector.close()

    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False)
    print(f"Saved pose CSV: {out_csv}  (frames={len(df)})")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=str)
    ap.add_argument("--out", default="data/processed/model4_engagement/pose.csv", type=str)
    ap.add_argument("--max-frames", default=-1, type=int)
    args = ap.parse_args()
    
    print("Starting pose extraction...")
    print(f"Video: {args.video}")
    print(f"Output: {args.out}")
    if args.max_frames > 0:
        print(f"Max frames: {args.max_frames}")
    
    run(Path(args.video), Path(args.out), max_frames=args.max_frames)
