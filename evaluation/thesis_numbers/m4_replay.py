"""
Throw-away REPORT_4 replay: score M4 on default feature vectors for every
reachable pose_ratio under a 3-frame buffer, then on three real MediaPipe
landmark buffers from latency-test videos.

Does not write to the database. Not imported by the application.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("ML_FUSION_THRESHOLD", "0.75")
os.environ.setdefault("ML_WINDOW_FRAMES", "3")

from app.services.ml_service import MLService  # noqa: E402

VIDEO_DIR = Path(r"D:\uni\6th sem\IRP\Data collection\raw data\participant 1")
VIDEOS = {
    "natural.mp4": VIDEO_DIR / "natural.mp4",
    "focused.mp4": VIDEO_DIR / "focused.mp4",
    "distracted.mp4": VIDEO_DIR / "distracted.mp4",
}
OUT = Path(__file__).resolve().parent / "raw" / "m4_replay.json"

DEFAULT_FEATS = {
    "lw_speed_mean": 0.0,
    "lw_speed_std": 0.0,
    "rw_speed_mean": 0.0,
    "rw_speed_std": 0.0,
    "lw_to_nose_mean": 0.5,
    "rw_to_nose_mean": 0.5,
    "lw_to_sh_mean": 0.3,
    "rw_to_sh_mean": 0.3,
    "nose_jitter": 0.0,
    "lw_below_sh_ratio": 0.5,
    "rw_below_sh_ratio": 0.5,
}


def score_eng(svc: MLService, feats: dict) -> float:
    X = np.array([[feats.get(c, 0.0) for c in svc.eng_feature_cols]], dtype=np.float32)
    return float(svc.eng_model.predict_proba(X)[0, 1])


def load_frame(video_name: str, frame_index: int) -> np.ndarray:
    path = VIDEOS[video_name]
    if not path.exists():
        raise FileNotFoundError(path)
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError(f"failed to read {video_name} frame {frame_index}")
    # Same preprocess as heartbeat latency test / frontend JPEG quality 0.5
    frame = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_LINEAR)
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    decoded = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return decoded


def main() -> None:
    svc = MLService()
    report: dict = {
        "note": "REPLAY — not stored session 94 data",
        "window_size": svc.window_size,
        "fusion_threshold": svc.fusion_threshold,
        "eng_feature_cols": list(svc.eng_feature_cols),
        "ml_mode": svc.ml_mode,
        "exhaustive_pose_ratio": [],
        "real_buffers": [],
    }

    # Exhaustive reachable pose_ratio values for buffers of length 1..3
    ratios = sorted({i / n for n in (1, 2, 3) for i in range(n + 1)})
    for pr in ratios:
        feats = {"pose_ratio": float(pr), **DEFAULT_FEATS}
        # Also confirm via compute_engagement_features with synthetic buffer:
        # n valid landmarks out of buf_len → pose_ratio = n/buf_len
        eng = score_eng(svc, feats)
        report["exhaustive_pose_ratio"].append(
            {"pose_ratio": float(pr), "features": feats, "engagement_prob": eng}
        )

    # Three distinct 3-observation buffers from different videos/frames
    buffer_specs = [
        {
            "name": "natural_early",
            "frames": [("natural.mp4", 0), ("natural.mp4", 10), ("natural.mp4", 20)],
        },
        {
            "name": "focused_mid",
            "frames": [("focused.mp4", 30), ("focused.mp4", 40), ("focused.mp4", 50)],
        },
        {
            "name": "distracted_late",
            "frames": [
                ("distracted.mp4", 60),
                ("distracted.mp4", 70),
                ("distracted.mp4", 80),
            ],
        },
    ]

    for spec in buffer_specs:
        sid = f"m4_replay_{spec['name']}"
        lm_buf = []
        frame_meta = []
        for video_name, idx in spec["frames"]:
            bgr = load_frame(video_name, idx)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            lm = svc.extract_landmarks(rgb, sid)
            lm_buf.append(lm)
            frame_meta.append(
                {
                    "video": video_name,
                    "frame_index": idx,
                    "landmark_present": lm is not None,
                    "landmark_keys": sorted(lm.keys()) if lm else None,
                }
            )
        feats = svc.compute_engagement_features(lm_buf)
        eng = score_eng(svc, feats)
        report["real_buffers"].append(
            {
                "name": spec["name"],
                "frames": frame_meta,
                "n_valid": sum(1 for lm in lm_buf if lm is not None),
                "buf_len": len(lm_buf),
                "features": feats,
                "engagement_prob": eng,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
