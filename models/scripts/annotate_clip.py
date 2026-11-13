"""OpenCV annotation player for model6 human distraction spans (PLAN 4).

Protocol (v4_distraction_spans):
  Mark every distraction span in all clips.
  Distracted clips: unmarked time = unlabelled (dropped at extract).
  Focused / natural clips: unmarked time = focused.
  Natural clips are evaluation-only.

Definition:
  Off-screen attention >= 2 s (phone, looking away, talking, absent, drowsy,
  eyes off the lesson). Glances < 2 s are NOT distraction.

Keys:
  D         start/end a distracted span (primary)
  F         start/end a focused span (corrections / on-task islands in distracted)
  U         undo last completed span
  X         delete the span under the playhead
  Space     pause / resume
  ← / → or , / .   seek −2 s / +2 s (clamped; never exits at EOF)
  1 / 2 / 4 playback speed
  S         save now
  Q / Esc   save and quit

Writes <clip_stem>_labels.csv next to the clip (outside the repo) with a
protocol_version header comment and columns start_sec,end_sec,label.

Usage (repo root):
  venvpy312\\Scripts\\python.exe models/scripts/annotate_clip.py --participant 1 --condition natural
  venvpy312\\Scripts\\python.exe models/scripts/annotate_clip.py --video "D:\\...\\focused.mp4"
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from models.src.model6_natural.intake import (  # noqa: E402
    DEFAULT_RAW_ROOT,
    discover_clips,
)

PROTOCOL_VERSION = "v4_distraction_spans"
DEFINITION = (
    "Distraction = off-screen attention >= 2 s "
    "(phone, looking away, talking, absent, drowsy, eyes off lesson). "
    "Glances < 2 s are NOT distraction. "
    "Mark every such span. Distracted clips: unmarked = dropped; "
    "focused/natural: unmarked = focused."
)

LabelSpan = Tuple[float, float, int]  # start, end, label (0 focused / 1 distracted)


def _labels_path(video: Path) -> Path:
    return video.with_name(f"{video.stem}_labels.csv")


def load_labels(path: Path) -> List[LabelSpan]:
    """Load existing spans once (no duplicates). Skips blank/# comment lines."""
    if not path.exists():
        return []
    out: List[LabelSpan] = []
    seen = set()
    with path.open("r", encoding="utf-8", newline="") as f:
        # Strip protocol header comments before DictReader
        rows = []
        for line in f:
            if line.lstrip().startswith("#") or not line.strip():
                continue
            rows.append(line)
    if not rows:
        return []
    reader = csv.DictReader(rows)
    for row in reader:
        if "start_sec" not in row or "end_sec" not in row or "label" not in row:
            continue
        span = (float(row["start_sec"]), float(row["end_sec"]), int(row["label"]))
        key = (round(span[0], 3), round(span[1], 3), span[2])
        if key in seen:
            continue
        seen.add(key)
        out.append(span)
    out.sort(key=lambda t: t[0])
    return out


def save_labels(path: Path, spans: List[LabelSpan]) -> None:
    cleaned = [(s, e, y) for s, e, y in spans if e > s + 1e-3]
    cleaned.sort(key=lambda t: t[0])
    # Deduplicate on write
    dedup: List[LabelSpan] = []
    seen = set()
    for s, e, y in cleaned:
        key = (round(s, 3), round(e, 3), y)
        if key in seen:
            continue
        seen.add(key)
        dedup.append((s, e, y))
    with path.open("w", newline="", encoding="utf-8") as f:
        f.write(f"# protocol_version={PROTOCOL_VERSION}\n")
        w = csv.writer(f)
        w.writerow(["start_sec", "end_sec", "label"])
        for s, e, y in dedup:
            w.writerow([f"{s:.3f}", f"{e:.3f}", int(y)])
    print(f"[annotate] wrote {path} ({len(dedup)} spans)")


def _overlay(frame, lines, color=(240, 240, 240)):
    y = 28
    for line in lines:
        cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
        y += 22


def _active_label(spans: List[LabelSpan], t: float, drafting: Optional[Tuple[float, int]]) -> Optional[int]:
    if drafting is not None and t >= drafting[0]:
        return drafting[1]
    for s, e, y in spans:
        if s <= t < e:
            return y
    return None


def _span_under_cursor(spans: List[LabelSpan], t: float) -> Optional[int]:
    for i, (s, e, _y) in enumerate(spans):
        if s <= t < e:
            return i
    return None


def annotate(video: Path, start_paused: bool = True) -> Path:
    print(DEFINITION)
    print(
        "Keys: D distract | F focused-correction | U undo | X delete-under-cursor | "
        "Space | ,/. seek 2s | 1/2/4 | S save | Q quit"
    )
    out_path = _labels_path(video)
    spans = load_labels(out_path)
    if spans:
        print(f"[annotate] loaded {len(spans)} existing spans from {out_path.name}")

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 15.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    # Prefer duration from msec seek (handles .MOV / VFR better than n/fps alone)
    if n_frames > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, n_frames - 1))
        duration_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        duration = (duration_ms / 1000.0) if duration_ms > 0 else (n_frames / fps)
    else:
        duration = 0.0
    last_idx = max(0, n_frames - 1) if n_frames > 0 else 0

    speed = 1.0
    paused = start_paused
    drafting: Optional[Tuple[float, int]] = None
    t_sec = 0.0
    win = f"annotate: {video.name}"

    def seek_to_sec(target: float) -> None:
        nonlocal t_sec
        target = float(np.clip(target, 0.0, max(duration - 1e-3, 0.0)))
        cap.set(cv2.CAP_PROP_POS_MSEC, target * 1000.0)
        # Clamp frame index after seek so EOF never exits the loop
        idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES) or 0)
        if n_frames > 0 and idx >= n_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, last_idx)
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, duration - 1.0 / max(fps, 1.0)) * 1000.0)
        t_sec = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0

    seek_to_sec(0.0)

    try:
        while True:
            wall0 = time.perf_counter()
            ok, frame = cap.read()
            if not ok:
                # EOF: clamp to last frame and pause — do not exit
                paused = True
                seek_to_sec(max(0.0, duration - 1.0 / max(fps, 1.0)))
                ok, frame = cap.read()
                if not ok:
                    # Last resort: black frame so the UI stays up
                    frame = np.zeros((360, 640, 3), dtype=np.uint8)
            t_sec = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0
            if duration > 0 and t_sec > duration:
                t_sec = duration

            if paused:
                # Hold position: re-seek so next iteration re-reads the same frame
                seek_to_sec(t_sec)

            view = frame.copy()
            lab = _active_label(spans, t_sec, drafting)
            lab_txt = {None: "-", 0: "FOCUSED", 1: "DISTRACTED"}[lab]
            draft_txt = (
                f"DRAFT {('D' if drafting[1] == 1 else 'F')} from {drafting[0]:.1f}s"
                if drafting
                else ""
            )
            _overlay(
                view,
                [
                    f"{video.name}  t={t_sec:6.1f}/{duration:6.1f}s  {speed:.0f}x  "
                    f"{'PAUSE' if paused else 'PLAY'}",
                    f"label={lab_txt}  spans={len(spans)}  {draft_txt}",
                    "D distract | F correct | U undo | X del | Space | ,/. | S | Q",
                ],
                color=(80, 220, 80)
                if lab == 0
                else ((80, 80, 240) if lab == 1 else (220, 220, 220)),
            )
            cv2.imshow(win, view)

            delay = 1 if paused else max(1, int(1000 / (fps * speed)))
            key = cv2.waitKeyEx(delay)
            if not paused:
                elapsed = time.perf_counter() - wall0
                target = 1.0 / (fps * speed)
                if elapsed < target:
                    extra = int((target - elapsed) * 1000)
                    if extra > 0:
                        k2 = cv2.waitKeyEx(extra)
                        if k2 != -1:
                            key = k2

            code = key & 0xFF if key != -1 else -1
            is_left = key in (2424832, 65361)
            is_right = key in (2555904, 65363)

            if code in (ord("q"), ord("Q"), 27):
                break
            if code == ord(" "):
                paused = not paused
            elif code == ord("1"):
                speed = 1.0
            elif code == ord("2"):
                speed = 2.0
            elif code == ord("4"):
                speed = 4.0
            elif code in (ord("s"), ord("S")):
                save_labels(out_path, spans)
            elif is_left or code == ord(","):
                seek_to_sec(t_sec - 2.0)
                paused = True
            elif is_right or code == ord("."):
                seek_to_sec(t_sec + 2.0)
                paused = True
            elif code in (ord("u"), ord("U")):
                if drafting is not None:
                    print(f"[annotate] cancel draft from {drafting[0]:.2f}s")
                    drafting = None
                elif spans:
                    removed = spans.pop()
                    print(f"[annotate] undo {removed[0]:.2f}-{removed[1]:.2f}s label={removed[2]}")
            elif code in (ord("x"), ord("X")):
                idx = _span_under_cursor(spans, t_sec)
                if idx is not None:
                    removed = spans.pop(idx)
                    print(f"[annotate] delete {removed[0]:.2f}-{removed[1]:.2f}s label={removed[2]}")
                else:
                    print("[annotate] no span under cursor")
            elif code in (ord("d"), ord("D")):
                if drafting is None:
                    drafting = (t_sec, 1)
                    print(f"[annotate] start distracted @ {t_sec:.2f}s")
                elif drafting[1] == 1:
                    end = max(t_sec, drafting[0] + 0.01)
                    spans.append((drafting[0], end, 1))
                    print(f"[annotate] end distracted {drafting[0]:.2f}-{end:.2f}s")
                    drafting = None
                else:
                    print("[annotate] finish the focused draft with F first")
            elif code in (ord("f"), ord("F")):
                if drafting is None:
                    drafting = (t_sec, 0)
                    print(f"[annotate] start focused @ {t_sec:.2f}s")
                elif drafting[1] == 0:
                    end = max(t_sec, drafting[0] + 0.01)
                    spans.append((drafting[0], end, 0))
                    print(f"[annotate] end focused {drafting[0]:.2f}-{end:.2f}s")
                    drafting = None
                else:
                    print("[annotate] finish the distracted draft with D first")
    finally:
        if drafting is not None:
            spans.append((drafting[0], max(drafting[0] + 0.01, t_sec), drafting[1]))
            print("[annotate] auto-closed open draft on exit")
        cap.release()
        cv2.destroyAllWindows()
        save_labels(out_path, spans)
    return out_path


def _resolve_video(args) -> Path:
    if args.video:
        return Path(args.video).resolve()
    clips = discover_clips(args.raw_root, probe=False)
    sid = f"S{args.participant:02d}"
    for c in clips:
        if c.subject_id == sid and c.condition == args.condition:
            return c.path
    raise FileNotFoundError(f"No {args.condition} clip for participant {args.participant}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Annotate distraction spans on a clip (PLAN 4)")
    p.add_argument("--video", type=Path, default=None)
    p.add_argument("--participant", type=int, default=None)
    p.add_argument(
        "--condition",
        choices=("focused", "distracted", "natural"),
        default="natural",
    )
    p.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    p.add_argument("--play", action="store_true", help="Start playing (default: paused)")
    args = p.parse_args(argv)
    if args.video is None and args.participant is None:
        p.error("pass --video PATH or --participant N")
    video = _resolve_video(args)
    print(f"[annotate] video={video}")
    annotate(video, start_paused=not args.play)


if __name__ == "__main__":
    main()
