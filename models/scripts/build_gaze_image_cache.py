"""Pack MPIIGaze eye-patch PNGs referenced by a CSV into one .npy array.

Per-file PNG opens are the training bottleneck on Windows (~25 img/s per
DataLoader worker). A single uint8 .npy (N, 36, 60) is memory-mapped by
MPIIGaze4Class when present next to the CSV as ``<csv_stem>_images.npy``,
so workers read from the OS page cache instead.

Usage (from models/):
    python scripts/build_gaze_image_cache.py data/processed/model1_gaze/train_stride4.csv
    python scripts/build_gaze_image_cache.py data/processed/model1_gaze/val.csv
    python scripts/build_gaze_image_cache.py data/processed/model1_gaze/test.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

H, W = 36, 60  # MPIIGaze normalized eye patch (height, width)


def build(csv_path: Path) -> Path:
    df = pd.read_csv(csv_path)
    out = csv_path.with_name(f"{csv_path.stem}_images.npy")
    arr = np.lib.format.open_memmap(out, mode="w+", dtype=np.uint8, shape=(len(df), H, W))
    for i, path in enumerate(df["img_path"]):
        img = Image.open(path).convert("L")
        a = np.asarray(img, dtype=np.uint8)
        if a.shape != (H, W):
            a = np.asarray(img.resize((W, H)), dtype=np.uint8)
        arr[i] = a
        if (i + 1) % 20000 == 0:
            print(f"  {i + 1:,}/{len(df):,}", flush=True)
    arr.flush()
    print(f"Saved {out}  shape={arr.shape}  {out.stat().st_size / 1e6:.0f} MB")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: build_gaze_image_cache.py <csv> [more csvs...]")
    for arg in sys.argv[1:]:
        print(f"Building cache for {arg}")
        build(Path(arg))
