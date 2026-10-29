"""Extract window features from participant clips (CPU MediaPipe)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

import cv2
import pandas as pd

# Allow `python -m models.src.model6_natural.extract` from repo root
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from models.src.features.face_pose import FrameFeatureExtractor  # noqa: E402
from models.src.features.windows import (  # noqa: E402
    WINDOW_FEATURE_NAMES,
    compute_pose_baseline,
    label_window_row,
    windows_from_frames,
)
from models.src.model6_natural.intake import (  # noqa: E402
    DEFAULT_RAW_ROOT,
    ClipSpec,
    discover_clips,
    write_manifest,
)


def _iter_sampled_frames(video_path: Path, target_fps: float = 5.0):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    native_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if native_fps <= 1e-3:
        native_fps = 15.0
    interval = max(1, int(round(native_fps / target_fps)))
    idx = 0
    kept = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % interval == 0:
            t_sec = idx / native_fps
            yield t_sec, frame
            kept += 1
        idx += 1
    cap.release()
    print(f"  sampled {kept} frames @ ~{target_fps} fps from {video_path.name}")


def extract_clip(
    clip: ClipSpec,
    window_secs: List[float],
    target_fps: float,
    baseline_from_focused: dict,
) -> List[dict]:
    """Extract windows for one clip. Uses subject focused-clip baseline when available."""
    extractor = FrameFeatureExtractor()
    try:
        frames = []
        for t_sec, frame in _iter_sampled_frames(clip.path, target_fps=target_fps):
            frames.append(extractor.process(frame, t_sec))
    finally:
        extractor.close()

    if not frames:
        return []

    yaw0 = pitch0 = None
    if clip.subject_id in baseline_from_focused:
        yaw0, pitch0 = baseline_from_focused[clip.subject_id]
    elif clip.condition == "focused":
        yaw0, pitch0 = compute_pose_baseline(frames, n_frames=30)
        baseline_from_focused[clip.subject_id] = (yaw0, pitch0)

    rows: List[dict] = []
    for wsec in window_secs:
        for win in windows_from_frames(
            frames, window_sec=wsec, hop_sec=1.0, yaw0=yaw0, pitch0=pitch0
        ):
            y = label_window_row(clip.condition, win)
            row = {
                "subject_id": clip.subject_id,
                "condition": clip.condition,
                "source_file": clip.path.name,
                "y": y if y is not None else -1,
                "in_train": int(y is not None),
                **{k: win[k] for k in ["window_start_sec", "window_sec", "yaw0", "pitch0"]},
                **{k: win[k] for k in WINDOW_FEATURE_NAMES},
            }
            rows.append(row)
    return rows


def run_extract(
    raw_root: Path,
    out_csv: Path,
    manifest_csv: Path,
    window_secs: List[float],
    target_fps: float,
) -> Path:
    clips = discover_clips(raw_root)
    if not clips:
        raise RuntimeError(f"No complete participants under {raw_root}")
    write_manifest(clips, manifest_csv)

    # Process focused clips first so baselines exist for distracted/natural
    order = {"focused": 0, "distracted": 1, "natural": 2}
    clips_sorted = sorted(clips, key=lambda c: (c.subject_id, order.get(c.condition, 9)))

    baselines: dict = {}
    all_rows: List[dict] = []
    for clip in clips_sorted:
        print(f"[extract] {clip.subject_id} {clip.condition} ← {clip.path}")
        rows = extract_clip(clip, window_secs, target_fps, baselines)
        print(f"  windows={len(rows)}")
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)

    meta = {
        "raw_root": str(raw_root),
        "n_rows": int(len(df)),
        "subjects": sorted(df["subject_id"].unique().tolist()),
        "window_secs": window_secs,
        "target_fps": target_fps,
        "features": WINDOW_FEATURE_NAMES,
        "label_note": (
            "y=0 focused/forced kept on-screen; y=1 distracted sustained off-task; "
            "y=-1 natural or dropped mismatched windows (in_train=0)"
        ),
        "baselines": {
            sid: {"yaw0": float(v[0]), "pitch0": float(v[1])} for sid, v in baselines.items()
        },
    }
    meta_path = out_csv.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[extract] wrote {out_csv} ({len(df)} rows)")
    print(f"[extract] wrote {meta_path}")
    return out_csv


def main(argv=None):
    p = argparse.ArgumentParser(description="Extract model6 window features")
    p.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    p.add_argument(
        "--out",
        type=Path,
        default=_REPO / "models" / "data" / "processed" / "model6_natural" / "windows.csv",
    )
    p.add_argument(
        "--manifest",
        type=Path,
        default=_REPO / "models" / "data" / "processed" / "model6_natural" / "manifest.csv",
    )
    p.add_argument("--fps", type=float, default=5.0)
    p.add_argument("--windows", type=float, nargs="+", default=[2.0, 5.0])
    args = p.parse_args(argv)
    run_extract(args.raw_root, args.out, args.manifest, list(args.windows), args.fps)


if __name__ == "__main__":
    main()
