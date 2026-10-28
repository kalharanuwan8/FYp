"""
Offline before/after face-gate measurement (no server, no webcam).

Compares the old Haar call used by MLService with a small grid of settings
(equalise + optional upscale + minSize / minNeighbors). Writes
raw/face_gate_check.json with face-found ratios and mean detection times.

Datasets:
  - BIWI pose test.csv (same yaw bins as REPORT.md section 6)
  - participant 1 natural / focused / distracted videos, resized 224 and
    JPEG quality 50 (same as browser / live_webcam_selftest)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional, Tuple

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
OUT = Path(__file__).resolve().parent / "raw"
OUT.mkdir(parents=True, exist_ok=True)

POSE_TEST = MODELS / "data" / "processed" / "model2_pose" / "test.csv"
PARTICIPANT_DIR = Path(r"D:\uni\6th sem\IRP\Data collection\raw data\participant 1")
VIDEOS = [
    PARTICIPANT_DIR / "natural.mp4",
    PARTICIPANT_DIR / "focused.mp4",
    PARTICIPANT_DIR / "distracted.mp4",
]

# Old deployed call (ml_service before this fix)
OLD = {"name": "old", "upscale": 1.0, "min_neighbors": 5, "min_size": 50, "equalize": False}

# Candidates: lower minSize (BIWI spot check found ~28px faces) and/or upscale.
CANDIDATES = [
    OLD,
    {"name": "ms28_n5", "upscale": 1.0, "min_neighbors": 5, "min_size": 28, "equalize": False},
    {"name": "eq_ms28_n4", "upscale": 1.0, "min_neighbors": 4, "min_size": 28, "equalize": True},
    {"name": "eq_ms36_n4", "upscale": 1.0, "min_neighbors": 4, "min_size": 36, "equalize": True},
    {"name": "eq_up2_ms50_n5", "upscale": 2.0, "min_neighbors": 5, "min_size": 50, "equalize": True},
    {"name": "eq_up2_ms40_n4", "upscale": 2.0, "min_neighbors": 4, "min_size": 40, "equalize": True},
    {"name": "eq_up2_ms28_n4", "upscale": 2.0, "min_neighbors": 4, "min_size": 28, "equalize": True},
]

YAW_BINS = [
    ("0-15", 0.0, 15.0),
    ("15-30", 15.0, 30.0),
    ("30-45", 30.0, 45.0),
    ("45-60", 45.0, 60.0),
    (">60", 60.0, None),
]


def yaw_bin(abs_yaw: float) -> Optional[str]:
    for label, lo, hi in YAW_BINS:
        if hi is None:
            if abs_yaw >= lo:
                return label
        elif lo <= abs_yaw < hi:
            return label
    return None


def detect_face(
    frame_bgr: np.ndarray,
    cascade: cv2.CascadeClassifier,
    *,
    upscale: float,
    min_neighbors: int,
    min_size: int,
    equalize: bool,
) -> Tuple[Optional[Tuple[int, int, int, int]], float]:
    """Return (box in original coords or None, elapsed seconds)."""
    t0 = time.perf_counter()
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    if equalize:
        gray = cv2.equalizeHist(gray)
    scale = float(upscale) if upscale and upscale > 0 else 1.0
    if abs(scale - 1.0) > 1e-6:
        gray_det = cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_LINEAR,
        )
    else:
        gray_det = gray
    faces = cascade.detectMultiScale(
        gray_det,
        scaleFactor=1.1,
        minNeighbors=int(min_neighbors),
        minSize=(int(min_size), int(min_size)),
    )
    elapsed = time.perf_counter() - t0
    if len(faces) == 0:
        return None, elapsed
    fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
    if abs(scale - 1.0) > 1e-6:
        fx = int(round(fx / scale))
        fy = int(round(fy / scale))
        fw = int(round(fw / scale))
        fh = int(round(fh / scale))
    h, w = frame_bgr.shape[:2]
    fx = max(0, min(fx, w - 1))
    fy = max(0, min(fy, h - 1))
    fw = max(1, min(fw, w - fx))
    fh = max(1, min(fh, h - fy))
    return (fx, fy, fw, fh), elapsed


def jpeg_roundtrip_224(frame_bgr: np.ndarray) -> np.ndarray:
    resized = cv2.resize(frame_bgr, (224, 224), interpolation=cv2.INTER_LINEAR)
    ok, buf = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    decoded = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if decoded is None:
        raise RuntimeError("jpeg decode failed")
    return decoded


def sample_video_frames(path: Path, max_frames: int = 60, stride: int = 15) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    if not path.exists():
        return frames
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return frames
    idx = 0
    while len(frames) < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            frames.append(jpeg_roundtrip_224(frame))
        idx += 1
    cap.release()
    return frames


def eval_settings(
    frames: list[np.ndarray],
    cascade: cv2.CascadeClassifier,
    settings: dict,
) -> dict[str, Any]:
    found = 0
    times: list[float] = []
    for frame in frames:
        box, elapsed = detect_face(
            frame,
            cascade,
            upscale=settings["upscale"],
            min_neighbors=settings["min_neighbors"],
            min_size=settings["min_size"],
            equalize=settings["equalize"],
        )
        times.append(elapsed)
        if box is not None:
            found += 1
    n = len(frames)
    return {
        "n": n,
        "n_face_found": found,
        "ratio_face_found": (None if n == 0 else found / n),
        "mean_detect_s": (None if not times else float(np.mean(times))),
    }


def eval_biwi(cascade: cv2.CascadeClassifier, settings: dict) -> dict[str, Any]:
    df = pd.read_csv(POSE_TEST)
    bin_found = {b[0]: 0 for b in YAW_BINS}
    bin_n = {b[0]: 0 for b in YAW_BINS}
    times: list[float] = []
    unreadable = 0
    for _, row in df.iterrows():
        name = yaw_bin(abs(float(row["yaw_deg"])))
        if name is None:
            continue
        # CSV paths are relative to models/ (same as run_model_metrics.py after chdir).
        img_path = Path(str(row["img_path"]))
        if not img_path.is_file():
            img_path = MODELS / img_path
        img = cv2.imread(str(img_path))
        if img is None:
            unreadable += 1
            continue
        box, elapsed = detect_face(
            img,
            cascade,
            upscale=settings["upscale"],
            min_neighbors=settings["min_neighbors"],
            min_size=settings["min_size"],
            equalize=settings["equalize"],
        )
        times.append(elapsed)
        bin_n[name] += 1
        if box is not None:
            bin_found[name] += 1
    bins_out = []
    total_n = 0
    total_found = 0
    for label, _, _ in YAW_BINS:
        n = bin_n[label]
        fnd = bin_found[label]
        total_n += n
        total_found += fnd
        bins_out.append(
            {
                "abs_yaw_bin": label,
                "n_readable": n,
                "n_face_found": fnd,
                "ratio_face_found": (None if n == 0 else fnd / n),
            }
        )
    return {
        "n_csv_rows": int(len(df)),
        "n_unreadable": unreadable,
        "n_readable_total": total_n,
        "n_face_found_total": total_found,
        "ratio_face_found_total": (None if total_n == 0 else total_found / total_n),
        "ratio_near_frontal_0_15": (
            None if bin_n["0-15"] == 0 else bin_found["0-15"] / bin_n["0-15"]
        ),
        "mean_detect_s": (None if not times else float(np.mean(times))),
        "bins": bins_out,
    }


def blank_control(cascade: cv2.CascadeClassifier, settings: dict, n: int = 20) -> dict[str, Any]:
    """Frames with no person — should stay near zero detections."""
    frames = [np.zeros((224, 224, 3), dtype=np.uint8) for _ in range(n)]
    # also a few mid-gray and noise frames
    frames += [np.full((224, 224, 3), 128, dtype=np.uint8) for _ in range(n)]
    rng = np.random.default_rng(0)
    frames += [rng.integers(0, 256, (224, 224, 3), dtype=np.uint8) for _ in range(n)]
    return eval_settings(frames, cascade, settings)


def main() -> None:
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    if cascade.empty():
        raise SystemExit("Haar cascade failed to load")

    video_frames: dict[str, list[np.ndarray]] = {}
    for path in VIDEOS:
        key = path.stem
        video_frames[key] = sample_video_frames(path)
        print(f"loaded {key}: {len(video_frames[key])} frames from {path}", flush=True)

    results = []
    for settings in CANDIDATES:
        print(f"eval {settings['name']} ...", flush=True)
        biwi = eval_biwi(cascade, settings)
        videos = {
            name: eval_settings(frames, cascade, settings)
            for name, frames in video_frames.items()
        }
        # focused + natural are "person present, often frontal / reading"
        person_n = 0
        person_found = 0
        for name in ("natural", "focused"):
            if name in videos and videos[name]["n"]:
                person_n += videos[name]["n"]
                person_found += videos[name]["n_face_found"]
        control = blank_control(cascade, settings)
        entry = {
            "settings": settings,
            "biwi": biwi,
            "participant1_videos": videos,
            "person_present_natural_focused": {
                "n": person_n,
                "n_face_found": person_found,
                "ratio_face_found": (None if person_n == 0 else person_found / person_n),
            },
            "empty_frame_control": control,
        }
        results.append(entry)

    # Choose: raise person-present and/or near-frontal BIWI vs old, without
    # empty-frame control detections rising above a small absolute count, and
    # without dropping person-present by more than 5 percentage points.
    old = next(r for r in results if r["settings"]["name"] == "old")
    old_frontal = old["biwi"]["ratio_near_frontal_0_15"]
    old_person = old["person_present_natural_focused"]["ratio_face_found"] or 0.0
    old_frontal_v = 0.0 if old_frontal is None else old_frontal

    chosen = old
    chosen_reason = "no candidate clearly better than old; keep old"
    best_score = -1.0
    for r in results:
        if r["settings"]["name"] == "old":
            continue
        control_found = r["empty_frame_control"]["n_face_found"]
        if control_found > 2:
            continue  # too many false faces on blank/noise
        frontal = r["biwi"]["ratio_near_frontal_0_15"]
        frontal_v = 0.0 if frontal is None else frontal
        person = r["person_present_natural_focused"]["ratio_face_found"] or 0.0
        if person + 1e-9 < old_person - 0.05:
            continue  # do not sacrifice person-present detection
        improved_person = person > old_person + 1e-9
        improved_frontal = frontal is not None and frontal_v > old_frontal_v + 0.05
        if not (improved_person or improved_frontal):
            continue
        score = person * 2.0 + frontal_v
        if score > best_score:
            best_score = score
            chosen = r
            chosen_reason = (
                f"best score={score:.4f}: person_present {person:.4f} "
                f"(old {old_person:.4f}), BIWI 0-15 {frontal_v:.4f} "
                f"(old {old_frontal_v:.4f}), empty_control_found={control_found}"
            )

    payload = {
        "label": "face_gate_check",
        "old_call": "detectMultiScale(gray, 1.1, 5, minSize=(50, 50))",
        "pose_test_csv": str(POSE_TEST),
        "participant_dir": str(PARTICIPANT_DIR),
        "candidates": results,
        "chosen": {
            "settings": chosen["settings"],
            "reason": chosen_reason,
            "biwi_ratio_near_frontal_0_15": chosen["biwi"]["ratio_near_frontal_0_15"],
            "person_present_ratio": chosen["person_present_natural_focused"]["ratio_face_found"],
            "empty_control_face_found": chosen["empty_frame_control"]["n_face_found"],
        },
    }
    out_path = OUT / "face_gate_check.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("WROTE", out_path, flush=True)
    print("CHOSEN", json.dumps(payload["chosen"], indent=2), flush=True)


if __name__ == "__main__":
    main()
