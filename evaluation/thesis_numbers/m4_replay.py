"""
Throw-away REPORT_4 replay against the *current* live MLService:
  - ML_WINDOW_FRAMES default 5
  - compute_engagement_features uses real movement features when n >= 2

Scores M4 on:
  1) the n < 2 default vector (fallback only)
  2) three real MediaPipe landmark buffers (length = window_size) from
     latency-test videos

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

# Match Run 5 fusion threshold; leave ML_WINDOW_FRAMES unset so the live default applies.
os.environ.setdefault("ML_FUSION_THRESHOLD", "0.75")
os.environ.pop("ML_WINDOW_FRAMES", None)

from app.services.ml_service import MLService  # noqa: E402

VIDEO_DIR = Path(r"D:\uni\6th sem\IRP\Data collection\raw data\participant 1")
VIDEOS = {
    "natural.mp4": VIDEO_DIR / "natural.mp4",
    "focused.mp4": VIDEO_DIR / "focused.mp4",
    "distracted.mp4": VIDEO_DIR / "distracted.mp4",
}
OUT = Path(__file__).resolve().parent / "raw" / "m4_replay.json"


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
    frame = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_LINEAR)
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def main() -> None:
    svc = MLService()
    w = int(svc.window_size)
    report: dict = {
        "note": "REPLAY against CURRENT live MLService — not stored session 94 data",
        "window_size": w,
        "fusion_threshold": svc.fusion_threshold,
        "eng_feature_cols": list(svc.eng_feature_cols),
        "ml_mode": svc.ml_mode,
        "default_fallback_n_lt_2": None,
        "real_buffers": [],
        "summary": {},
    }

    # Default path (n < 2): empty / single None buffer
    default_feats = svc.compute_engagement_features([None])
    default_prob = score_eng(svc, default_feats)
    report["default_fallback_n_lt_2"] = {
        "features": default_feats,
        "engagement_prob": default_prob,
    }

    # Three distinct buffers of length = current window_size
    # Frame indices spaced so landmarks differ across videos/poses.
    buffer_specs = [
        {
            "name": "natural_early",
            "frames": [("natural.mp4", i * 5) for i in range(w)],
        },
        {
            "name": "focused_mid",
            "frames": [("focused.mp4", 30 + i * 5) for i in range(w)],
        },
        {
            "name": "distracted_late",
            "frames": [("distracted.mp4", 50 + i * 5) for i in range(w)],
        },
    ]

    probs = []
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
                }
            )
        feats = svc.compute_engagement_features(lm_buf)
        eng = score_eng(svc, feats)
        probs.append(eng)
        report["real_buffers"].append(
            {
                "name": spec["name"],
                "frames": frame_meta,
                "n_valid": sum(1 for lm in lm_buf if lm is not None),
                "buf_len": len(lm_buf),
                "features": {k: (float(v) if isinstance(v, (float, np.floating, int)) else v)
                             for k, v in feats.items()},
                "engagement_prob": eng,
                "uses_default_vector": (
                    feats.get("lw_to_nose_mean") == 0.5
                    and feats.get("lw_speed_mean") == 0.0
                    and feats.get("lw_to_sh_mean") == 0.3
                    and float(feats.get("pose_ratio", -1)) == float(len([x for x in lm_buf if x]) / max(len(lm_buf), 1))
                    and all(
                        abs(float(feats.get(k, 0)) - float(default_feats.get(k, 0))) < 1e-12
                        for k in svc.eng_feature_cols
                        if k != "pose_ratio"
                    )
                ),
            }
        )

    distinct = sorted(set(round(p, 12) for p in probs))
    report["summary"] = {
        "n_buffers": len(probs),
        "engagement_probs": probs,
        "n_distinct_probs": len(distinct),
        "min_prob": min(probs) if probs else None,
        "max_prob": max(probs) if probs else None,
        "default_fallback_prob": default_prob,
        "all_equal_to_default": all(abs(p - default_prob) < 1e-12 for p in probs),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
