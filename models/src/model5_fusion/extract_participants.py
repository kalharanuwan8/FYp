"""
Replay the late-fusion heartbeat path (face gate → M1 → M2 baseline → M3 →
5-heartbeat window → 9 features) over the 7 participant recordings.

Does not touch the live monitoring pipeline. Weights are loaded from
models/outputs/checkpoints_late_fusion/ via env vars.

Usage (from the models/ directory):
  ..\\venvpy312\\Scripts\\python.exe -u -m src.model5_fusion.extract_participants
"""
from __future__ import annotations

import csv
import os
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[3]
MODELS = REPO / "models"
RAW_ROOT = Path(
    os.environ.get(
        "PARTICIPANT_RAW_ROOT",
        r"D:\uni\6th sem\IRP\Data collection\raw data",
    )
)
OUT_DIR = MODELS / "data" / "processed" / "model5_fusion_participants"
STAGE = MODELS / "outputs" / "checkpoints_late_fusion"

HEARTBEAT_SEC = 2.0
OFFSETS = (0.0, 0.5, 1.0, 1.5)
WINDOW_SIZE = 5
JPEG_QUALITY = 70
OUT_SIZE = 224

FEAT_COLS = [
    "p_center_mean",
    "p_left_mean",
    "p_right_mean",
    "p_down_mean",
    "gaze_away_ratio",
    "yaw_mean",
    "pitch_mean",
    "roll_mean",
    "engagement_prob_mean",
]


def _configure_env() -> None:
    """Point MLService at staging weights before the singleton is created."""
    os.environ["GAZE_CKPT"] = str(STAGE / "model1_gaze" / "best.pt")
    os.environ["POSE_CKPT"] = str(STAGE / "model2_pose" / "best.pt")
    os.environ["ENG_CKPT"] = str(STAGE / "model4_engagement" / "model.pkl")
    # Force the 9-feature fusion pack so fusion_feat_names match live late-fusion.
    os.environ["FUSION_CKPT"] = str(STAGE / "model5_fusion" / "model.pkl")
    # Avoid accidental live-path preference if face landmarker is present.
    for p in (str(REPO), str(MODELS), str(REPO / "backend")):
        if p not in sys.path:
            sys.path.insert(0, p)


def _label_from_stem(stem: str) -> Optional[int]:
    s = stem.lower()
    if s == "distracted":
        return 1
    if s in ("focused", "forced"):
        return 0
    if s == "natural":
        return None  # eval-only
    return None


def _discover_videos(root: Path) -> List[Tuple[str, Path, Optional[int], str]]:
    """Return (participant, path, y_or_None, video_stem)."""
    rows = []
    for pdir in sorted(root.glob("participant *")):
        if not pdir.is_dir():
            continue
        pid = pdir.name.replace("participant ", "P").replace(" ", "")
        # Normalize "participant 1" → "P01"
        num = "".join(ch for ch in pdir.name if ch.isdigit())
        pid = f"P{int(num):02d}" if num else pdir.name
        for path in sorted(pdir.iterdir()):
            if path.suffix.lower() not in (".mp4", ".mov", ".avi", ".mkv"):
                continue
            y = _label_from_stem(path.stem)
            rows.append((pid, path, y, path.stem.lower()))
    return rows


def _center_square_224(frame_bgr: np.ndarray) -> np.ndarray:
    h, w = frame_bgr.shape[:2]
    side = min(h, w)
    x0 = (w - side) // 2
    y0 = (h - side) // 2
    crop = frame_bgr[y0 : y0 + side, x0 : x0 + side]
    return cv2.resize(crop, (OUT_SIZE, OUT_SIZE), interpolation=cv2.INTER_AREA)


def _jpeg_roundtrip(frame_bgr: np.ndarray) -> np.ndarray:
    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    if not ok:
        return frame_bgr
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def _nine_features(
    ml,
    session_id: Any,
    gaze_buf: List,
    pose_buf: List,
    lm_buf: List,
) -> Dict[str, float]:
    eng_prob = 0.5
    if ml.eng_model is not None and ml.eng_feature_cols:
        eng_feats = ml.compute_engagement_features(lm_buf)
        eng_X = np.array(
            [[eng_feats.get(c, 0.0) for c in ml.eng_feature_cols]],
            dtype=np.float32,
        )
        try:
            eng_prob = float(ml.eng_model.predict_proba(eng_X)[0, 1])
        except Exception:
            eng_prob = 0.5
    pose_for_score, _, _ = ml._centered_pose_buf(session_id, pose_buf)
    # Temporarily force the 9 live features regardless of pack contents.
    saved = list(ml.fusion_feat_names)
    ml.fusion_feat_names = list(FEAT_COLS)
    try:
        vec = ml.build_fusion_features(
            list(gaze_buf),
            list(pose_for_score),
            eng_prob,
            lm_buf=list(lm_buf),
            face_detected=True,
        ).reshape(-1)
    finally:
        ml.fusion_feat_names = saved
    return {name: float(vec[i]) for i, name in enumerate(FEAT_COLS)}


def _process_offset(
    ml,
    video_path: Path,
    participant: str,
    video_stem: str,
    y: Optional[int],
    offset: float,
    window_writer,
    hb_writer,
) -> Tuple[int, int, int]:
    """Returns (n_sampled, n_face, n_windows)."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"  [skip] cannot open {video_path}")
        return 0, 0, 0

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 1e-3:
        fps = 25.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = n_frames / fps if n_frames > 0 else 0.0

    sid = f"{participant}_{video_stem}_off{offset:.1f}"
    ml.clear_session(sid)

    gaze_buf: Deque = deque(maxlen=WINDOW_SIZE)
    pose_buf: Deque = deque(maxlen=WINDOW_SIZE)
    lm_buf: Deque = deque(maxlen=WINDOW_SIZE)

    n_sampled = n_face = n_windows = 0
    t = float(offset)
    while t <= duration + 1e-6:
        frame_idx = int(round(t * fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok or frame is None or getattr(frame, "size", 0) == 0:
            t += HEARTBEAT_SEC
            continue

        n_sampled += 1
        prepared = _jpeg_roundtrip(_center_square_224(frame))
        face_box = ml._detect_face(prepared)
        if face_box is None:
            hb_writer.writerow(
                [
                    participant,
                    video_stem,
                    f"{offset:.1f}",
                    f"{t:.3f}",
                    0,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    y if y is not None else "",
                ]
            )
            t += HEARTBEAT_SEC
            continue

        n_face += 1
        gaze_probs, pose_xyz, lm, meta = ml._infer_frame_signals(
            prepared, sid, face_box=face_box
        )
        ml._update_pose_baseline(sid, pose_xyz)

        gaze_buf.append(gaze_probs)
        pose_buf.append(pose_xyz)
        lm_buf.append(lm)

        hb_writer.writerow(
            [
                participant,
                video_stem,
                f"{offset:.1f}",
                f"{t:.3f}",
                1,
                f"{float(gaze_probs[0]):.6f}",
                f"{float(gaze_probs[1]):.6f}",
                f"{float(gaze_probs[2]):.6f}",
                f"{float(gaze_probs[3]):.6f}",
                f"{float(pose_xyz[0]):.4f}",
                f"{float(pose_xyz[1]):.4f}",
                f"{float(pose_xyz[2]):.4f}",
                y if y is not None else "",
            ]
        )

        if len(gaze_buf) >= WINDOW_SIZE:
            feats = _nine_features(ml, sid, list(gaze_buf), list(pose_buf), list(lm_buf))
            row = [feats[c] for c in FEAT_COLS]
            row.extend(
                [
                    y if y is not None else -1,
                    participant,
                    video_stem,
                    f"{offset:.1f}",
                    f"{t:.3f}",
                ]
            )
            window_writer.writerow(row)
            n_windows += 1

        t += HEARTBEAT_SEC

    cap.release()
    ml.clear_session(sid)
    return n_sampled, n_face, n_windows


def main() -> None:
    _configure_env()
    from app.services.ml_service import MLService

    # Reset singleton if a previous import left a different pack loaded.
    MLService._instance = None
    ml = MLService()
    print(
        f"[extract] ml_mode={ml.ml_mode} device={ml.device} "
        f"gaze={ml.gaze_model is not None} pose={ml.pose_model is not None} "
        f"eng={ml.eng_model is not None}"
    )
    if ml.gaze_model is None or ml.pose_model is None or ml.eng_model is None:
        raise SystemExit("Staging M1/M2/M3 weights failed to load; aborting.")
    if ml.device != "cuda":
        print("[extract] WARNING: CUDA not active; continuing on CPU")

    ml.window_size = WINDOW_SIZE
    ml.pose_baseline_frames = 8
    ml.fusion_feat_names = list(FEAT_COLS)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    windows_path = OUT_DIR / "windows.csv"
    hb_path = OUT_DIR / "heartbeats.csv"
    summary_path = OUT_DIR / "extract_summary.csv"

    videos = _discover_videos(RAW_ROOT)
    if not videos:
        raise SystemExit(f"No videos under {RAW_ROOT}")

    print(f"[extract] {len(videos)} videos under {RAW_ROOT}")
    t0 = time.time()

    with windows_path.open("w", newline="", encoding="utf-8") as wf, hb_path.open(
        "w", newline="", encoding="utf-8"
    ) as hf, summary_path.open("w", newline="", encoding="utf-8") as sf:
        ww = csv.writer(wf)
        hw = csv.writer(hf)
        sw = csv.writer(sf)
        ww.writerow(FEAT_COLS + ["y", "participant", "video", "offset", "t_sec"])
        hw.writerow(
            [
                "participant",
                "video",
                "offset",
                "t_sec",
                "face",
                "p_center",
                "p_left",
                "p_right",
                "p_down",
                "yaw",
                "pitch",
                "roll",
                "y",
            ]
        )
        sw.writerow(
            [
                "participant",
                "video",
                "y",
                "offset",
                "n_sampled",
                "n_face",
                "n_windows",
                "face_rate",
            ]
        )

        for i, (pid, path, y, stem) in enumerate(videos, 1):
            print(f"[{i}/{len(videos)}] {pid} {stem} ({path.name}) y={y}")
            for off in OFFSETS:
                ns, nf, nw = _process_offset(ml, path, pid, stem, y, off, ww, hw)
                rate = (nf / ns) if ns else 0.0
                sw.writerow(
                    [
                        pid,
                        stem,
                        y if y is not None else "natural",
                        f"{off:.1f}",
                        ns,
                        nf,
                        nw,
                        f"{rate:.3f}",
                    ]
                )
                print(
                    f"  offset={off:.1f} sampled={ns} face={nf} "
                    f"windows={nw} face_rate={rate:.2f}"
                )
                wf.flush()
                hf.flush()
                sf.flush()

    elapsed = time.time() - t0
    print(f"[extract] done in {elapsed/60:.1f} min → {windows_path}")


if __name__ == "__main__":
    main()
