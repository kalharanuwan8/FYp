"""Cache per-frame MediaPipe features for every model6 clip (restartable).

Writes one CSV per clip under:
  models/data/processed/model6_natural/frames/<S0x>_<cond>.csv

Columns are the FrameFeatures fields. Re-running skips clips whose CSV
already exists and has at least one data row (delete the file to redo).

Usage (repo root, CPU, ~13k frames @ 2 fps):
    venvpy312\\Scripts\\python.exe -m models.src.model6_natural.cache_frames
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict, fields
from pathlib import Path
from typing import Iterable, List

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from models.src.features.face_pose import FrameFeatureExtractor, FrameFeatures  # noqa: E402
from models.src.model6_natural.extract import _iter_sampled_frames  # noqa: E402
from models.src.model6_natural.intake import (  # noqa: E402
    DEFAULT_RAW_ROOT,
    ClipSpec,
    discover_clips,
    write_manifest,
)

FRAME_FIELDNAMES = [f.name for f in fields(FrameFeatures)]
DEFAULT_FRAMES_DIR = _REPO / "models" / "data" / "processed" / "model6_natural" / "frames"
DEFAULT_MANIFEST = _REPO / "models" / "data" / "processed" / "model6_natural" / "manifest.csv"
TARGET_FPS = 2.0


def frame_csv_path(frames_dir: Path, clip: ClipSpec) -> Path:
    return frames_dir / f"{clip.subject_id}_{clip.condition}.csv"


def _csv_is_done(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 32:
        return False
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            row = next(reader, None)
            return bool(header) and bool(row)
    except OSError:
        return False


def write_frame_csv(path: Path, frames: Iterable[FrameFeatures]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    n = 0
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FRAME_FIELDNAMES)
        w.writeheader()
        for fr in frames:
            row = asdict(fr)
            row["face_present"] = int(bool(row["face_present"]))
            row["body_present"] = int(bool(row["body_present"]))
            w.writerow(row)
            n += 1
    tmp.replace(path)
    return n


def cache_clip(clip: ClipSpec, out_csv: Path, target_fps: float) -> int:
    extractor = FrameFeatureExtractor()
    try:
        frames: List[FrameFeatures] = []
        for t_sec, frame in _iter_sampled_frames(clip.path, target_fps=target_fps):
            frames.append(extractor.process(frame, t_sec))
    finally:
        extractor.close()
    return write_frame_csv(out_csv, frames)


def run_cache(
    raw_root: Path,
    frames_dir: Path,
    manifest_csv: Path,
    target_fps: float = TARGET_FPS,
    force: bool = False,
) -> List[Path]:
    clips = [c for c in discover_clips(raw_root) if c.condition != "protocol"]
    if not clips:
        raise RuntimeError(f"No clips under {raw_root}")
    write_manifest(clips, manifest_csv)

    # Focused first so a later extract pass can build pose baselines in order.
    order = {"focused": 0, "distracted": 1, "natural": 2}
    clips_sorted = sorted(clips, key=lambda c: (c.subject_id, order.get(c.condition, 9)))

    written: List[Path] = []
    for clip in clips_sorted:
        out = frame_csv_path(frames_dir, clip)
        if not force and _csv_is_done(out):
            print(f"[cache] skip {out.name} (exists)")
            written.append(out)
            continue
        print(f"[cache] {clip.subject_id} {clip.condition} ← {clip.path.name}")
        n = cache_clip(clip, out, target_fps)
        print(f"  frames={n} → {out}")
        written.append(out)
    return written


def main(argv=None):
    p = argparse.ArgumentParser(description="Cache per-frame model6 features")
    p.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    p.add_argument("--frames-dir", type=Path, default=DEFAULT_FRAMES_DIR)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--fps", type=float, default=TARGET_FPS)
    p.add_argument("--force", action="store_true", help="Rebuild existing frame CSVs")
    args = p.parse_args(argv)
    run_cache(args.raw_root, args.frames_dir, args.manifest, args.fps, args.force)


if __name__ == "__main__":
    main()
