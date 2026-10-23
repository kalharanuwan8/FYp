# model1_gaze Data preparation
# src/model1_gaze/prepare.py
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from PIL import Image
from scipy.io import loadmat
from tqdm import tqdm


# -----------------------------
# Config
# -----------------------------
@dataclass(frozen=True)
class PrepConfig:
    # Update if your dataset root is different
    mpiigaze_root: Path = Path("data/raw/mpiigaze/MPIIGaze")

    out_root: Path = Path("data/processed/model1_gaze")
    out_images: Path = Path("data/processed/model1_gaze/images")

    # Subject split (subject-wise split)
    train_subjects: Tuple[str, ...] = tuple([f"p{n:02d}" for n in range(0, 11)])   # p00..p10
    val_subjects: Tuple[str, ...] = tuple([f"p{n:02d}" for n in range(11, 13)])    # p11..p12
    test_subjects: Tuple[str, ...] = tuple([f"p{n:02d}" for n in range(13, 15)])   # p13..p14

    # Thresholds for "center" in radians (~10 degrees)
    yaw_thr: float = math.radians(10.0)
    pitch_thr: float = math.radians(10.0)

    # Export settings
    export_images: bool = True  # recommended
    overwrite_images: bool = False  # set True if you want to regenerate PNGs


LABEL_MAP: Dict[str, int] = {"center": 0, "left": 1, "right": 2, "up": 3, "down": 4}


# -----------------------------
# Helpers
# -----------------------------
def parse_day_num(day_mat: Path) -> str:
    # e.g. day01.mat -> day01
    m = re.match(r"(day\d{2})\.mat$", day_mat.name)
    return m.group(1) if m else day_mat.stem


def gaze_vec_to_yaw_pitch(g: np.ndarray) -> Tuple[float, float]:
    """
    g: (3,) gaze vector [gx, gy, gz]
    Returns yaw, pitch in radians.
    Convention used:
      yaw   = atan2(gx, -gz)
      pitch = atan2(gy, sqrt(gx^2 + gz^2))
    """
    gx, gy, gz = float(g[0]), float(g[1]), float(g[2])
    yaw = math.atan2(gx, -gz)
    pitch = math.atan2(gy, math.sqrt(gx * gx + gz * gz))
    return yaw, pitch


def yaw_pitch_to_class(yaw: float, pitch: float, yaw_thr: float, pitch_thr: float) -> str:
    # Center region
    if abs(yaw) < yaw_thr and abs(pitch) < pitch_thr:
        return "center"

    # Dominant axis decides direction
    if abs(yaw) >= abs(pitch):
        return "left" if yaw < 0 else "right"
    else:
        return "down" if pitch > 0 else "up"



def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def save_eye_image(img_arr: np.ndarray, out_path: Path, overwrite: bool) -> None:
    """
    img_arr: (H,W) grayscale. Save as 8-bit PNG.
    """
    if out_path.exists() and not overwrite:
        return

    # Robust conversion to uint8
    arr = np.array(img_arr)
    if arr.dtype != np.uint8:
        # If already 0..255 floats or ints, clip; else normalize
        amin, amax = float(arr.min()), float(arr.max())
        if amax <= 255.0 and amin >= 0.0:
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        else:
            # Normalize to 0..255
            if amax - amin < 1e-6:
                arr = np.zeros_like(arr, dtype=np.uint8)
            else:
                arr = ((arr - amin) / (amax - amin) * 255.0).clip(0, 255).astype(np.uint8)

    im = Image.fromarray(arr, mode="L")
    ensure_dir(out_path.parent)
    im.save(out_path)


def load_mat_day(path: Path):
    """
    Loads a single dayXX.mat and returns (filenames, left_struct, right_struct)
    """
    m = loadmat(path, squeeze_me=True, struct_as_record=False)
    filenames = m["filenames"]  # typically array/list of strings
    data = m["data"]
    left = data.left
    right = data.right
    return filenames, left, right


def normalize_filenames(filenames) -> List[str]:
    """
    Convert filenames object from scipy loadmat to list of strings.
    Example: ["0001.jpg", "0002.jpg", ...]
    """
    if isinstance(filenames, (list, tuple)):
        return [str(x) for x in filenames]
    # numpy array
    fn = np.array(filenames).tolist()
    if isinstance(fn, (list, tuple)):
        return [str(x) for x in fn]
    return [str(fn)]


# -----------------------------
# Main
# -----------------------------
def run(cfg: PrepConfig) -> None:
    data_norm_root = cfg.mpiigaze_root / "Data" / "Normalized"
    assert data_norm_root.exists(), f"Not found: {data_norm_root}"

    ensure_dir(cfg.out_root)
    ensure_dir(cfg.out_images)

    # Save label map
    with open(cfg.out_root / "label_map.json", "w", encoding="utf-8") as f:
        json.dump(LABEL_MAP, f, indent=2)

    rows: List[Dict] = []

    subjects = sorted([p.name for p in data_norm_root.iterdir() if p.is_dir() and p.name.startswith("p")])
    if not subjects:
        raise RuntimeError(f"No subjects found under {data_norm_root}")

    print(f"Found subjects: {subjects}")

    for subject in subjects:
        subj_dir = data_norm_root / subject
        day_mats = sorted(subj_dir.glob("day*.mat"))
        if not day_mats:
            print(f"[WARN] No .mat files for {subject} at {subj_dir}")
            continue

        for day_mat in tqdm(day_mats, desc=f"Reading {subject}", leave=False):
            day = parse_day_num(day_mat)
            filenames, left, right = load_mat_day(day_mat)
            filenames_list = normalize_filenames(filenames)

            # left.image: (N, H, W), left.gaze: (N, 3), same for right
            # Depending on scipy parsing, sometimes shape can be weird - ensure numpy arrays
            left_images = np.array(left.image)
            right_images = np.array(right.image)
            left_gaze = np.array(left.gaze)
            right_gaze = np.array(right.gaze)

            # Ensure gaze arrays have correct shape (N, 3)
            # Sometimes scipy.loadmat returns unexpected shapes - handle edge cases
            if left_gaze.ndim == 0:
                # Scalar value - cannot use
                print(f"[ERROR] {subject}/{day}: left_gaze is a scalar (ndim=0), expected array")
                continue
            elif left_gaze.ndim == 1:
                # If 1D with 3 elements, reshape to (1, 3)
                if left_gaze.shape[0] == 3:
                    left_gaze = left_gaze.reshape(1, 3)
                else:
                    print(f"[ERROR] {subject}/{day}: left_gaze has unexpected 1D shape {left_gaze.shape}")
                    continue
            elif left_gaze.ndim == 2 and left_gaze.shape[1] != 3:
                print(f"[ERROR] {subject}/{day}: left_gaze shape is {left_gaze.shape}, expected (N, 3)")
                continue

            if right_gaze.ndim == 0:
                # Scalar value - cannot use
                print(f"[ERROR] {subject}/{day}: right_gaze is a scalar (ndim=0), expected array")
                continue
            elif right_gaze.ndim == 1:
                # If 1D with 3 elements, reshape to (1, 3)
                if right_gaze.shape[0] == 3:
                    right_gaze = right_gaze.reshape(1, 3)
                else:
                    print(f"[ERROR] {subject}/{day}: right_gaze has unexpected 1D shape {right_gaze.shape}")
                    continue
            elif right_gaze.ndim == 2 and right_gaze.shape[1] != 3:
                print(f"[ERROR] {subject}/{day}: right_gaze shape is {right_gaze.shape}, expected (N, 3)")
                continue

            n = len(filenames_list)
            if left_images.shape[0] != n or right_images.shape[0] != n:
                # Still proceed but guard
                n = min(n, left_images.shape[0], right_images.shape[0], left_gaze.shape[0], right_gaze.shape[0])

            for i in range(n):
                fname = filenames_list[i]  # e.g. "0001.jpg"
                stem = Path(fname).stem     # "0001"

                # RIGHT eye sample
                g = right_gaze[i]
                yaw, pitch = gaze_vec_to_yaw_pitch(g)
                cls = yaw_pitch_to_class(yaw, pitch, cfg.yaw_thr, cfg.pitch_thr)

                out_img_path = cfg.out_images / subject / day / f"right_{stem}.png"
                if cfg.export_images:
                    save_eye_image(right_images[i], out_img_path, cfg.overwrite_images)

                rows.append({
                    "img_path": str(out_img_path.as_posix()) if cfg.export_images else f"{day_mat.as_posix()}::right::{i}",
                    "label": LABEL_MAP[cls],
                    "label_name": cls,
                    "subject_id": subject,
                    "day": day,
                    "eye": "right",
                    "gaze_x": float(g[0]),
                    "gaze_y": float(g[1]),
                    "gaze_z": float(g[2]),
                    "yaw_rad": float(yaw),
                    "pitch_rad": float(pitch),
                })

                # LEFT eye sample
                g2 = left_gaze[i]
                yaw2, pitch2 = gaze_vec_to_yaw_pitch(g2)
                cls2 = yaw_pitch_to_class(yaw2, pitch2, cfg.yaw_thr, cfg.pitch_thr)

                out_img_path2 = cfg.out_images / subject / day / f"left_{stem}.png"
                if cfg.export_images:
                    save_eye_image(left_images[i], out_img_path2, cfg.overwrite_images)

                rows.append({
                    "img_path": str(out_img_path2.as_posix()) if cfg.export_images else f"{day_mat.as_posix()}::left::{i}",
                    "label": LABEL_MAP[cls2],
                    "label_name": cls2,
                    "subject_id": subject,
                    "day": day,
                    "eye": "left",
                    "gaze_x": float(g2[0]),
                    "gaze_y": float(g2[1]),
                    "gaze_z": float(g2[2]),
                    "yaw_rad": float(yaw2),
                    "pitch_rad": float(pitch2),
                })

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("No samples extracted. Check dataset paths and .mat contents.")

    # Split by subject
    train_df = df[df["subject_id"].isin(cfg.train_subjects)].reset_index(drop=True)
    val_df = df[df["subject_id"].isin(cfg.val_subjects)].reset_index(drop=True)
    test_df = df[df["subject_id"].isin(cfg.test_subjects)].reset_index(drop=True)

    # Save
    train_csv = cfg.out_root / "train.csv"
    val_csv = cfg.out_root / "val.csv"
    test_csv = cfg.out_root / "test.csv"

    train_df.to_csv(train_csv, index=False)
    val_df.to_csv(val_csv, index=False)
    test_df.to_csv(test_csv, index=False)

    # Stats
    def stats(name: str, part: pd.DataFrame) -> None:
        print(f"\n{name}: {len(part):,} samples")
        if len(part) == 0:
            return
        counts = part["label_name"].value_counts()
        print(counts.to_string())
        print("yaw range (deg):",
              f"{math.degrees(part['yaw_rad'].min()):.1f} .. {math.degrees(part['yaw_rad'].max()):.1f}")
        print("pitch range (deg):",
              f"{math.degrees(part['pitch_rad'].min()):.1f} .. {math.degrees(part['pitch_rad'].max()):.1f}")

    print("\nSaved:")
    print(" -", train_csv)
    print(" -", val_csv)
    print(" -", test_csv)
    print(" -", cfg.out_root / "label_map.json")

    stats("TRAIN", train_df)
    stats("VAL", val_df)
    stats("TEST", test_df)


if __name__ == "__main__":
    cfg = PrepConfig()
    run(cfg)
