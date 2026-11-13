"""Discover participant clips under the Data collection raw-data tree."""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2

# Raw clips live outside the repo (participant video is not committed).
# Override with MODEL6_RAW_ROOT; the default is the original collection folder.
DEFAULT_RAW_ROOT = Path(
    os.environ.get(
        "MODEL6_RAW_ROOT",
        str(Path(__file__).resolve().parents[5] / "Data collection" / "raw data"),
    )
)

# focused / forced are the same instructed-studying class (case-insensitive stems)
FOCUSED_STEMS = ("focused", "forced")
FOCUSED_NAMES = ("focused.mp4", "forced.mp4")  # legacy alias
DISTRACTED_STEM = "distracted"
DISTRACTED_NAME = "distracted.mp4"  # legacy alias
NATURAL_STEM = "natural"
NATURAL_NAME = "natural.mp4"  # legacy alias
VIDEO_EXTS = (".mp4", ".mov")
# Scripted protocol recording (models/scripts/record_protocol.py)
PROTOCOL_NAME = "protocol.mp4"
PROTOCOL_LABELS_NAME = "protocol_labels.csv"


@dataclass(frozen=True)
class ClipSpec:
    subject_id: str
    condition: str  # focused | distracted | natural | protocol
    path: Path
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    duration_sec: Optional[float] = None

    @property
    def labels_path(self) -> Optional[Path]:
        if self.condition != "protocol":
            # Human annotation sidecar: <stem>_labels.csv next to the clip
            return self.path.with_name(f"{self.path.stem}_labels.csv")
        return self.path.with_name(PROTOCOL_LABELS_NAME)


def _participant_id(folder_name: str) -> Optional[str]:
    m = re.match(r"participant\s+(\d+)$", folder_name.strip(), flags=re.IGNORECASE)
    if not m:
        return None
    return f"S{int(m.group(1)):02d}"


def _find_by_stem(folder: Path, stem: str) -> Optional[Path]:
    """Case-insensitive match of ``stem`` + video extension under ``folder``."""
    want = stem.lower()
    for p in folder.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in VIDEO_EXTS:
            continue
        if p.stem.lower() == want:
            return p.resolve()
    return None


def _find_focused(folder: Path) -> Optional[Path]:
    for stem in FOCUSED_STEMS:
        found = _find_by_stem(folder, stem)
        if found is not None:
            return found
    return None


def probe_video(path: Path) -> Tuple[Optional[int], Optional[int], Optional[float], Optional[float]]:
    """Return (width, height, fps, duration_sec) via OpenCV; Nones on failure."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None, None, None, None
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or None
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) or None
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if fps <= 1e-3:
            fps = None
        n_frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        duration = (n_frames / fps) if (fps and n_frames > 0) else None
        return width, height, fps, duration
    finally:
        cap.release()


def _with_probe(spec: ClipSpec) -> ClipSpec:
    w, h, fps, dur = probe_video(spec.path)
    return ClipSpec(
        subject_id=spec.subject_id,
        condition=spec.condition,
        path=spec.path,
        width=w,
        height=h,
        fps=fps,
        duration_sec=dur,
    )


def discover_clips(raw_root: Path = DEFAULT_RAW_ROOT, probe: bool = True) -> List[ClipSpec]:
    """Return clips for participants that have distracted + focused/forced + natural."""
    if not raw_root.exists():
        raise FileNotFoundError(f"Raw data root missing: {raw_root}")

    clips: List[ClipSpec] = []
    for child in sorted(raw_root.iterdir()):
        if not child.is_dir():
            continue
        sid = _participant_id(child.name)
        if sid is None:
            continue

        protocol = child / PROTOCOL_NAME
        if protocol.exists() and (child / PROTOCOL_LABELS_NAME).exists():
            spec = ClipSpec(sid, "protocol", protocol.resolve())
            clips.append(_with_probe(spec) if probe else spec)
            print(f"[intake] {sid}: protocol={protocol.name}")

        distracted = _find_by_stem(child, DISTRACTED_STEM)
        natural = _find_by_stem(child, NATURAL_STEM)
        focused = _find_focused(child)

        # Skip empty / incomplete participants
        if not (distracted and natural and focused is not None):
            if not protocol.exists():
                print(f"[intake] skip {child.name}: incomplete clip set")
            continue

        for cond, path in (
            ("distracted", distracted),
            ("focused", focused),
            ("natural", natural),
        ):
            spec = ClipSpec(sid, cond, path)
            clips.append(_with_probe(spec) if probe else spec)

        print(
            f"[intake] {sid}: distracted={distracted.name}, "
            f"focused={focused.name}, natural={natural.name}"
        )
    return clips


def subjects_from_clips(clips: List[ClipSpec]) -> List[str]:
    return sorted({c.subject_id for c in clips})


def write_manifest(clips: List[ClipSpec], out_csv: Path) -> Path:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "subject_id",
                "condition",
                "file",
                "source_name",
                "width",
                "height",
                "fps",
                "duration_sec",
            ],
        )
        w.writeheader()
        for c in clips:
            w.writerow(
                {
                    "subject_id": c.subject_id,
                    "condition": c.condition,
                    "file": str(c.path),
                    "source_name": c.path.name,
                    "width": c.width if c.width is not None else "",
                    "height": c.height if c.height is not None else "",
                    "fps": f"{c.fps:.4f}" if c.fps is not None else "",
                    "duration_sec": f"{c.duration_sec:.3f}" if c.duration_sec is not None else "",
                }
            )
    return out_csv


def clips_by_subject(clips: List[ClipSpec]) -> Dict[str, List[ClipSpec]]:
    out: Dict[str, List[ClipSpec]] = {}
    for c in clips:
        out.setdefault(c.subject_id, []).append(c)
    return out


if __name__ == "__main__":
    found = discover_clips()
    out = Path(__file__).resolve().parents[3] / "models" / "data" / "processed" / "model6_natural" / "manifest.csv"
    write_manifest(found, out)
    print(f"[intake] {len(found)} clips → {out}")
