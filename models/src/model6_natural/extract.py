"""Extract window features from participant clips (CPU MediaPipe).

Modes:
  --from-cache   build windows from cached frame CSVs (see cache_frames.py)
  --labels human distraction_spans policy (PLAN 4)
  --labels rule / protocol / both   legacy paths
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from models.src.features.face_pose import FrameFeatureExtractor, FrameFeatures  # noqa: E402
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

# PLAN 4: 0.6 so 3–4 s annotated spans still yield positives.
MIN_LABEL_COVER = 0.6
DEFAULT_FRAMES_DIR = _REPO / "models" / "data" / "processed" / "model6_natural" / "frames"


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


def load_protocol_labels(path: Path) -> List[Tuple[float, float, str, int]]:
    df = pd.read_csv(path)
    for c in ("start_sec", "end_sec", "phase", "y"):
        if c not in df.columns:
            raise ValueError(f"{path} missing column {c}")
    return [
        (float(r.start_sec), float(r.end_sec), str(r.phase), int(r.y))
        for r in df.sort_values("start_sec").itertuples()
    ]


def load_human_labels(path: Path) -> List[Tuple[float, float, str, int]]:
    """Read <clip>_labels.csv (start_sec,end_sec,label), skipping # comment headers."""
    rows_raw = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.lstrip().startswith("#") or not line.strip():
                continue
            rows_raw.append(line)
    if not rows_raw:
        return []
    df = pd.read_csv(__import__("io").StringIO("".join(rows_raw)))
    if "label" not in df.columns:
        raise ValueError(f"{path} missing column label")
    for c in ("start_sec", "end_sec"):
        if c not in df.columns:
            raise ValueError(f"{path} missing column {c}")
    rows = []
    for r in df.sort_values("start_sec").itertuples():
        y = int(r.label)
        if y not in (0, 1):
            raise ValueError(f"{path}: label must be 0 or 1, got {y}")
        phase = "focused" if y == 0 else "distracted"
        rows.append((float(r.start_sec), float(r.end_sec), phase, y))
    return rows


def distraction_span_segments(
    condition: str, duration_sec: float, overlays: List[Tuple[float, float, str, int]]
) -> List[Tuple[float, float, str, int]]:
    """PLAN 4 distraction_spans policy.

    focused/natural: default y=0; annotated distraction spans → 1; F spans → 0.
    distracted: default unlabelled (y=-1, dropped); spans → 1; F corrections → 0.
    """
    cond = condition.lower()
    if cond in ("focused", "forced", "natural"):
        base_y, base_phase = 0, cond
    elif cond == "distracted":
        base_y, base_phase = -1, "unlabelled"
    else:
        return list(overlays)

    pieces: List[Tuple[float, float, str, int]] = [
        (0.0, float(duration_sec), base_phase, base_y)
    ]
    for o0, o1, ophase, oy in sorted(overlays, key=lambda s: s[0]):
        nxt: List[Tuple[float, float, str, int]] = []
        for s0, s1, phase, y in pieces:
            if s1 <= o0 or s0 >= o1:
                nxt.append((s0, s1, phase, y))
                continue
            if s0 < o0:
                nxt.append((s0, o0, phase, y))
            if s1 > o1:
                nxt.append((o1, s1, phase, y))
        nxt.append((o0, o1, ophase, oy))
        pieces = sorted(nxt, key=lambda s: s[0])
    return pieces


def merge_annotation_segments(
    base: List[Tuple[float, float, str, int]],
    overlays: List[Tuple[float, float, str, int]],
) -> List[Tuple[float, float, str, int]]:
    """Legacy overlay helper (protocol / older human path)."""
    if not overlays:
        return list(base)
    pieces = list(base)
    for o0, o1, ophase, oy in sorted(overlays, key=lambda s: s[0]):
        nxt: List[Tuple[float, float, str, int]] = []
        for s0, s1, phase, y in pieces:
            if s1 <= o0 or s0 >= o1:
                nxt.append((s0, s1, phase, y))
                continue
            if s0 < o0:
                nxt.append((s0, o0, phase, y))
            if s1 > o1:
                nxt.append((o1, s1, phase, y))
        nxt.append((o0, o1, ophase, oy))
        pieces = sorted(nxt, key=lambda s: s[0])
    return pieces


def default_segments(condition: str, duration_sec: float) -> List[Tuple[float, float, str, int]]:
    mapping = {"focused": 0, "forced": 0, "distracted": 1, "natural": 0}
    y = mapping.get(condition.lower())
    if y is None:
        return []
    return [(0.0, float(duration_sec), condition, int(y))]


def label_from_segments(
    segments: List[Tuple[float, float, str, int]],
    start: float,
    length: float,
    min_cover: float = MIN_LABEL_COVER,
) -> Tuple[Optional[int], str]:
    """Return (y, phase) when one segment covers >= min_cover of the window."""
    end = start + length
    best_phase, best_y, best_cov = "transition", None, 0.0
    for s0, s1, phase, y in segments:
        cov = max(0.0, min(end, s1) - max(start, s0)) / max(length, 1e-6)
        if cov > best_cov:
            best_phase, best_y, best_cov = phase, y, cov
    if best_cov < min_cover:
        return None, "transition"
    if best_y not in (0, 1):
        return None, best_phase  # unlabelled / dropped
    return best_y, best_phase


def load_frames_csv(path: Path) -> List[FrameFeatures]:
    frames: List[FrameFeatures] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            frames.append(
                FrameFeatures(
                    t_sec=float(row["t_sec"]),
                    face_present=bool(int(float(row["face_present"]))),
                    yaw=float(row["yaw"]),
                    pitch=float(row["pitch"]),
                    roll=float(row["roll"]),
                    iris_x=float(row["iris_x"]),
                    iris_y=float(row["iris_y"]),
                    blink=float(row["blink"]),
                    jaw_open=float(row["jaw_open"]),
                    hand_to_face=float(row["hand_to_face"]),
                    body_motion=float(row["body_motion"]),
                    nose_x=float(row["nose_x"]),
                    nose_y=float(row["nose_y"]),
                    body_present=bool(int(float(row.get("body_present", "0")))),
                )
            )
    return frames


def _clip_duration(clip: ClipSpec, frames: List[FrameFeatures]) -> float:
    if clip.duration_sec and clip.duration_sec > 0:
        return float(clip.duration_sec)
    if frames:
        return float(frames[-1].t_sec)
    return 0.0


def _unpack_baseline(b) -> Tuple[float, float, float]:
    if b is None:
        return 0.0, 0.0, 0.0
    if len(b) == 2:
        return float(b[0]), float(b[1]), 0.0
    return float(b[0]), float(b[1]), float(b[2])


def extract_clip(
    clip: ClipSpec,
    window_secs: List[float],
    target_fps: float,
    baseline_from_focused: dict,
    labels: str = "rule",
    frames: Optional[List[FrameFeatures]] = None,
    baseline_mode: str = "focused",
) -> List[dict]:
    """Extract windows for one clip."""
    if frames is None:
        extractor = FrameFeatureExtractor()
        try:
            frames = []
            for t_sec, frame in _iter_sampled_frames(clip.path, target_fps=target_fps):
                frames.append(extractor.process(frame, t_sec))
        finally:
            extractor.close()

    if not frames:
        return []

    yaw0 = pitch0 = roll0 = None
    segments = None
    clip_condition = clip.condition  # never overwrite with span phase names

    if clip.condition == "protocol":
        yaw0, pitch0, roll0 = compute_pose_baseline(frames, n_frames=30)
        segments = load_protocol_labels(clip.labels_path)
    elif labels == "human":
        duration = _clip_duration(clip, frames)
        overlays = []
        labels_path = clip.labels_path
        if labels_path is not None and labels_path.exists():
            overlays = load_human_labels(labels_path)
            print(f"  human labels: {labels_path.name} ({len(overlays)} spans)")
        else:
            print("  human labels: none")
        segments = distraction_span_segments(clip.condition, duration, overlays)

        # Natural: per-clip live-style baseline. Training clips: focused-clip baseline.
        use_live = baseline_mode == "live" or clip.condition == "natural"
        if use_live:
            yaw0, pitch0, roll0 = compute_pose_baseline(frames, n_frames=30)
        elif clip.subject_id in baseline_from_focused:
            yaw0, pitch0, roll0 = _unpack_baseline(baseline_from_focused[clip.subject_id])
        elif clip.condition == "focused":
            yaw0, pitch0, roll0 = compute_pose_baseline(frames, n_frames=30)
            baseline_from_focused[clip.subject_id] = (yaw0, pitch0, roll0)
        else:
            yaw0, pitch0, roll0 = compute_pose_baseline(frames, n_frames=30)
    elif clip.subject_id in baseline_from_focused:
        yaw0, pitch0, roll0 = _unpack_baseline(baseline_from_focused[clip.subject_id])
    elif clip.condition == "focused":
        yaw0, pitch0, roll0 = compute_pose_baseline(frames, n_frames=30)
        baseline_from_focused[clip.subject_id] = (yaw0, pitch0, roll0)

    rows: List[dict] = []
    for wsec in window_secs:
        for win in windows_from_frames(
            frames,
            window_sec=wsec,
            hop_sec=1.0,
            yaw0=yaw0,
            pitch0=pitch0,
            roll0=roll0,
        ):
            if segments is not None:
                y, _phase = label_from_segments(
                    segments, win["window_start_sec"], win["window_sec"]
                )
            else:
                y = label_window_row(clip.condition, win)
            eval_only = int(clip.condition == "natural")
            in_train = int(y is not None and not eval_only)
            row = {
                "subject_id": clip.subject_id,
                "condition": clip_condition,
                "source_file": clip.path.name,
                "y": y if y is not None else -1,
                "in_train": in_train,
                "eval_only": eval_only,
                **{k: win[k] for k in ["window_start_sec", "window_sec", "yaw0", "pitch0"]},
                "roll0": win.get("roll0", roll0 or 0.0),
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
    labels: str = "human",
    from_cache: bool = False,
    frames_dir: Path = DEFAULT_FRAMES_DIR,
    baseline_mode: str = "focused",
) -> Path:
    clips = discover_clips(raw_root)
    if labels == "rule":
        clips = [c for c in clips if c.condition != "protocol"]
    elif labels == "protocol":
        clips = [c for c in clips if c.condition == "protocol"]
    elif labels == "human":
        clips = [c for c in clips if c.condition != "protocol"]
    if not clips:
        raise RuntimeError(f"No clips for labels={labels} under {raw_root}")
    write_manifest(clips, manifest_csv)

    order = {"focused": 0, "distracted": 1, "natural": 2}
    clips_sorted = sorted(clips, key=lambda c: (c.subject_id, order.get(c.condition, 9)))

    baselines: dict = {}
    all_rows: List[dict] = []
    for clip in clips_sorted:
        print(f"[extract] {clip.subject_id} {clip.condition} ← {clip.path}")
        cached = None
        if from_cache:
            from models.src.model6_natural.cache_frames import frame_csv_path

            csv_path = frame_csv_path(frames_dir, clip)
            if not csv_path.exists():
                raise FileNotFoundError(
                    f"Missing frame cache {csv_path}; run cache_frames.py first"
                )
            cached = load_frames_csv(csv_path)
            print(f"  loaded {len(cached)} frames from {csv_path.name}")
        rows = extract_clip(
            clip,
            window_secs,
            target_fps,
            baselines,
            labels=labels,
            frames=cached,
            baseline_mode=baseline_mode,
        )
        print(f"  windows={len(rows)}")
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)

    label_source_map = {
        "rule": "rule (circular)",
        "protocol": "protocol",
        "both": "mixed rule + protocol",
        "human": "human_annotation / distraction_spans",
    }
    meta = {
        "raw_root": str(raw_root),
        "n_rows": int(len(df)),
        "subjects": sorted(df["subject_id"].unique().tolist()) if len(df) else [],
        "window_secs": window_secs,
        "target_fps": target_fps,
        "from_cache": bool(from_cache),
        "baseline_mode": baseline_mode,
        "frames_dir": str(frames_dir) if from_cache else None,
        "features": WINDOW_FEATURE_NAMES,
        "label_source": label_source_map[labels],
        "min_label_cover": MIN_LABEL_COVER,
        "label_note": (
            "distraction_spans: focused/natural default 0 + D→1; "
            "distracted default dropped + D→1 / F→0; "
            "eval_only=1 for natural; cover>="
            f"{MIN_LABEL_COVER}"
        ),
        "baselines": {
            sid: {
                "yaw0": float(v[0]),
                "pitch0": float(v[1]),
                "roll0": float(v[2]) if len(v) > 2 else 0.0,
            }
            for sid, v in baselines.items()
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
        default=_REPO / "models" / "data" / "processed" / "model6_natural" / "windows_v4.csv",
    )
    p.add_argument(
        "--manifest",
        type=Path,
        default=_REPO / "models" / "data" / "processed" / "model6_natural" / "manifest.csv",
    )
    p.add_argument("--fps", type=float, default=2.0)
    p.add_argument("--windows", type=float, nargs="+", default=[5.0])
    p.add_argument(
        "--labels",
        choices=("rule", "protocol", "both", "human"),
        default="human",
        help="human=distraction_spans (PLAN 4 default)",
    )
    p.add_argument("--from-cache", action="store_true")
    p.add_argument("--frames-dir", type=Path, default=DEFAULT_FRAMES_DIR)
    p.add_argument(
        "--baseline",
        choices=("focused", "live"),
        default="focused",
        help="focused=use focused-clip baseline for train clips; live=per-clip always",
    )
    args = p.parse_args(argv)
    run_extract(
        args.raw_root,
        args.out,
        args.manifest,
        list(args.windows),
        args.fps,
        args.labels,
        from_cache=args.from_cache,
        frames_dir=args.frames_dir,
        baseline_mode=args.baseline,
    )


if __name__ == "__main__":
    main()
