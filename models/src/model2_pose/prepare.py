# model2_pose Data preparation
# src/model2_pose/prepare.py
# BIWI head pose dataset -> clean CSVs + optional resized/copy images
#
# Expected raw structure (yours):
# data/raw/biwi/faces_0/<subject_id>/frame_00003_rgb.png
# data/raw/biwi/faces_0/<subject_id>/frame_00003_pose   (text)
#
# Output:
# data/processed/model2_pose/
#   train.csv, val.csv, test.csv, meta.json
#   images/<subject_id>/frame_00003.png  (optional copy/resize)

from __future__ import annotations
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image
from tqdm import tqdm


# -------------------------
# Config
# -------------------------
@dataclass
class Config:
    raw_root: Path = Path("data/raw/biwi")
    faces_dir: str = "faces_0"

    out_root: Path = Path("data/processed/model2_pose")
    out_images: Path = Path("data/processed/model2_pose/images")

    # If True: copy & resize RGB frames to out_images (recommended)
    export_images: bool = True
    img_size: int = 224  # resize to 224x224

    # Subject-wise split (edit if you want)
    train_subjects: Tuple[str, ...] = tuple(f"{i:02d}" for i in range(1, 15))  # 01-14
    val_subjects: Tuple[str, ...] = tuple(f"{i:02d}" for i in range(15, 18))  # 15-17
    test_subjects: Tuple[str, ...] = tuple(f"{i:02d}" for i in range(18, 21)) # 18-20


# -------------------------
# Pose parsing utils
# -------------------------
_FLOAT_RE = re.compile(r"[-+]?\d*\.\d+|[-+]?\d+")

def _read_floats(p: Path) -> List[float]:
    txt = p.read_text(errors="ignore")
    return [float(x) for x in _FLOAT_RE.findall(txt)]

def _rotation_to_ypr_deg(R: np.ndarray) -> Tuple[float, float, float]:
    """
    Convert rotation matrix to yaw/pitch/roll (degrees).
    Convention used: ZYX (yaw around Z, pitch around Y, roll around X)
    Many BIWI pose labels use a similar convention; even if sign differs,
    it's still valid for regression training in your project.

    Returns: (yaw_deg, pitch_deg, roll_deg)
    """
    # Guard for numerical noise
    R = R.astype(np.float64)
    sy = math.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])

    singular = sy < 1e-6

    if not singular:
        roll = math.atan2(R[2, 1], R[2, 2])
        pitch = math.atan2(-R[2, 0], sy)
        yaw = math.atan2(R[1, 0], R[0, 0])
    else:
        # Gimbal lock fallback
        roll = math.atan2(-R[1, 2], R[1, 1])
        pitch = math.atan2(-R[2, 0], sy)
        yaw = 0.0

    return (math.degrees(yaw), math.degrees(pitch), math.degrees(roll))

def parse_pose_file(pose_path: Path) -> Tuple[float, float, float]:
    """
    Robust parser for BIWI 'frame_xxxx_pose' text files.

    Common cases:
    - 12 floats: 3x3 rotation + 3 translation (R|t)
    - 16 floats: 4x4 matrix
    - 9 floats: 3x3 rotation only
    - 3 floats: already yaw/pitch/roll (rare)

    We only need yaw/pitch/roll.
    """
    vals = _read_floats(pose_path)
    n = len(vals)

    if n == 3:
        # Assume already yaw pitch roll in degrees
        yaw, pitch, roll = vals
        return float(yaw), float(pitch), float(roll)

    if n == 9:
        R = np.array(vals, dtype=np.float64).reshape(3, 3)
        return _rotation_to_ypr_deg(R)

    if n == 12:
        # 3x4 (R|t) -> first 9 are rotation
        R = np.array(vals[:9], dtype=np.float64).reshape(3, 3)
        return _rotation_to_ypr_deg(R)

    if n == 16:
        M = np.array(vals, dtype=np.float64).reshape(4, 4)
        R = M[:3, :3]
        return _rotation_to_ypr_deg(R)

    # If format is unexpected, try to salvage: take first 9 as rotation
    if n > 9:
        R = np.array(vals[:9], dtype=np.float64).reshape(3, 3)
        return _rotation_to_ypr_deg(R)

    raise ValueError(f"Unsupported pose format: {pose_path} has {n} floats")


# -------------------------
# Image export
# -------------------------
def export_rgb(rgb_path: Path, out_path: Path, size: int):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(rgb_path).convert("RGB")
    if size is not None:
        im = im.resize((size, size), Image.BILINEAR)
    im.save(out_path)


# -------------------------
# Main build
# -------------------------
def build_split(subject_ids: Tuple[str, ...], cfg: Config) -> List[Dict]:
    rows = []
    faces_root = cfg.raw_root / cfg.faces_dir

    for sid in subject_ids:
        subj_dir = faces_root / sid
        if not subj_dir.exists():
            print(f"[WARN] Missing subject folder: {subj_dir}")
            continue

        rgb_files = sorted(subj_dir.glob("frame_*_rgb.png"))
        if not rgb_files:
            print(f"[WARN] No rgb frames in: {subj_dir}")
            continue

        for rgb in rgb_files:
            # frame_00003_rgb.png -> frame_00003_pose
            frame_id = rgb.stem.replace("_rgb", "")  # frame_00003
            pose_path = subj_dir / f"{frame_id}_pose"
            if not pose_path.exists():
                # Some dumps might name it 'frame_00003_pose.txt' etc; try fallback
                alt = list(subj_dir.glob(f"{frame_id}_pose*"))
                if alt:
                    pose_path = alt[0]
                else:
                    continue

            try:
                yaw, pitch, roll = parse_pose_file(pose_path)
            except Exception:
                # Skip bad lines/files
                continue

            if cfg.export_images:
                out_img = cfg.out_images / sid / f"{frame_id}.png"
                export_rgb(rgb, out_img, cfg.img_size)
                img_path = out_img.as_posix()
            else:
                img_path = rgb.as_posix()

            rows.append({
                "img_path": img_path,
                "yaw_deg": yaw,
                "pitch_deg": pitch,
                "roll_deg": roll,
                "subject_id": sid,
                "frame_id": frame_id,
            })

    return rows


def save_csv(rows: List[Dict], out_csv: Path):
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    cols = ["img_path", "yaw_deg", "pitch_deg", "roll_deg", "subject_id", "frame_id"]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        import csv
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def summarize(rows: List[Dict], name: str):
    if not rows:
        print(f"{name}: 0 samples")
        return
    yaw = np.array([r["yaw_deg"] for r in rows], dtype=np.float64)
    pitch = np.array([r["pitch_deg"] for r in rows], dtype=np.float64)
    roll = np.array([r["roll_deg"] for r in rows], dtype=np.float64)
    print(f"{name}: {len(rows):,} samples")
    print(f"  yaw   range (deg): {yaw.min():.1f} .. {yaw.max():.1f}")
    print(f"  pitch range (deg): {pitch.min():.1f} .. {pitch.max():.1f}")
    print(f"  roll  range (deg): {roll.min():.1f} .. {roll.max():.1f}")


def run():
    cfg = Config()

    cfg.out_root.mkdir(parents=True, exist_ok=True)
    if cfg.export_images:
        cfg.out_images.mkdir(parents=True, exist_ok=True)

    train_rows = build_split(cfg.train_subjects, cfg)
    val_rows = build_split(cfg.val_subjects, cfg)
    test_rows = build_split(cfg.test_subjects, cfg)

    save_csv(train_rows, cfg.out_root / "train.csv")
    save_csv(val_rows, cfg.out_root / "val.csv")
    save_csv(test_rows, cfg.out_root / "test.csv")

    meta = {
        "raw_root": str(cfg.raw_root.as_posix()),
        "faces_dir": cfg.faces_dir,
        "export_images": cfg.export_images,
        "img_size": cfg.img_size,
        "splits": {
            "train_subjects": list(cfg.train_subjects),
            "val_subjects": list(cfg.val_subjects),
            "test_subjects": list(cfg.test_subjects),
        },
        "columns": ["img_path", "yaw_deg", "pitch_deg", "roll_deg", "subject_id", "frame_id"],
        "note": "Yaw/Pitch/Roll derived from rotation matrix using ZYX convention. Signs may differ by convention but OK for regression training.",
    }
    (cfg.out_root / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("\nSaved:")
    print(f" - {cfg.out_root/'train.csv'}")
    print(f" - {cfg.out_root/'val.csv'}")
    print(f" - {cfg.out_root/'test.csv'}")
    print(f" - {cfg.out_root/'meta.json'}")
    if cfg.export_images:
        print(f" - images in {cfg.out_images}")

    print()
    summarize(train_rows, "TRAIN")
    summarize(val_rows, "VAL")
    summarize(test_rows, "TEST")


if __name__ == "__main__":
    run()
