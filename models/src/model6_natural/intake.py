"""Discover participant clips under the Data collection raw-data tree."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_RAW_ROOT = Path(r"D:\uni\6th sem\IRP\Data collection\raw data")

# focused.mp4 and forced.mp4 are the same instructed-studying class
FOCUSED_NAMES = ("focused.mp4", "forced.mp4")
DISTRACTED_NAME = "distracted.mp4"
NATURAL_NAME = "natural.mp4"


@dataclass(frozen=True)
class ClipSpec:
    subject_id: str
    condition: str  # focused | distracted | natural
    path: Path


def _participant_id(folder_name: str) -> Optional[str]:
    m = re.match(r"participant\s+(\d+)$", folder_name.strip(), flags=re.IGNORECASE)
    if not m:
        return None
    return f"S{int(m.group(1)):02d}"


def discover_clips(raw_root: Path = DEFAULT_RAW_ROOT) -> List[ClipSpec]:
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

        distracted = child / DISTRACTED_NAME
        natural = child / NATURAL_NAME
        focused: Optional[Path] = None
        for name in FOCUSED_NAMES:
            cand = child / name
            if cand.exists():
                focused = cand
                break

        # Skip empty / incomplete participants (e.g. participant 4)
        if not (distracted.exists() and natural.exists() and focused is not None):
            print(f"[intake] skip {child.name}: incomplete clip set")
            continue

        clips.append(ClipSpec(sid, "distracted", distracted.resolve()))
        clips.append(ClipSpec(sid, "focused", focused.resolve()))
        clips.append(ClipSpec(sid, "natural", natural.resolve()))
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
            fieldnames=["subject_id", "condition", "file", "source_name"],
        )
        w.writeheader()
        for c in clips:
            w.writerow(
                {
                    "subject_id": c.subject_id,
                    "condition": c.condition,
                    "file": str(c.path),
                    "source_name": c.path.name,
                }
            )
    return out_csv


def clips_by_subject(clips: List[ClipSpec]) -> Dict[str, List[ClipSpec]]:
    out: Dict[str, List[ClipSpec]] = {}
    for c in clips:
        out.setdefault(c.subject_id, []).append(c)
    return out
