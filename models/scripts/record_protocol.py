"""Record one participant through the scripted distraction protocol.

Shows on-screen instructions for each phase and writes, into
<raw_root>/participant N/:

  protocol.mp4          webcam video (delete after feature extraction)
  protocol_labels.csv   start_sec,end_sec,phase,y   (y: 0 focused, 1 distracted, -1 unlabeled)

Labels come from the protocol timeline, not from any model feature, so they
are independent of what model6 sees. Phase boundaries are logged when the
prompt changes; the participant needs a second or two to react, which is why
extract.label_from_segments only labels windows mostly inside one phase.

Usage (repo root):
    venvpy312\\Scripts\\python.exe models/scripts/record_protocol.py --participant 5
    ... --quick   (10 s per phase, for a dry run)
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import cv2

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from models.src.model6_natural.intake import (  # noqa: E402
    DEFAULT_RAW_ROOT,
    PROTOCOL_LABELS_NAME,
    PROTOCOL_NAME,
)

# (phase, seconds, y, instruction). Order matters: the session opens with
# reading so the pose baseline (first face-present frames) is on-task, as live.
PHASES = [
    ("read", 180, 0, "Read the lesson on screen. Stay on task."),
    ("phone", 90, 1, "Use your phone (scroll / text) as you normally would."),
    ("read", 60, 0, "Back to reading the lesson."),
    ("away_talk", 90, 1, "Look away and talk to the person next to you."),
    ("lecture_video", 180, 0, "Watch the lecture video on screen."),
    ("leave_chair", 60, 1, "Stand up and step away from the desk."),
    ("read", 60, 0, "Sit down and continue reading."),
    ("natural", 120, -1, "Study however you like. (Not labeled.)"),
]


def _overlay(frame, lines, color=(255, 255, 255)):
    y = 30
    for line in lines:
        cv2.putText(frame, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)
        y += 26


def record(participant: int, raw_root: Path, camera: int, quick: bool) -> Path:
    out_dir = raw_root / f"participant {participant}"
    out_dir.mkdir(parents=True, exist_ok=True)
    video_path = out_dir / PROTOCOL_NAME
    labels_path = out_dir / PROTOCOL_LABELS_NAME
    if video_path.exists():
        raise FileExistsError(f"{video_path} exists — refusing to overwrite")

    cap = cv2.VideoCapture(camera, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera {camera}")
    fps = 15.0
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (640, 480))

    segments = []
    frame_idx = 0
    try:
        for i, (phase, secs, y, text) in enumerate(PHASES):
            secs = 10 if quick else secs
            # Timestamps are video time (frame_idx / fps), matching extract.py.
            start = frame_idx / fps
            n_frames = int(secs * fps)
            next_frame_t = time.perf_counter()
            for k in range(n_frames):
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Camera read failed")
                frame = cv2.resize(frame, (640, 480))
                writer.write(frame)  # the saved video has no overlay
                frame_idx += 1
                preview = cv2.flip(frame, 1)
                left = secs - k / fps
                _overlay(
                    preview,
                    [f"Phase {i + 1}/{len(PHASES)}: {phase}", text, f"{left:5.0f} s left   (q = abort)"],
                )
                cv2.imshow("protocol", preview)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    raise KeyboardInterrupt
                next_frame_t += 1.0 / fps
                time.sleep(max(0.0, next_frame_t - time.perf_counter()))
            segments.append((start, frame_idx / fps, phase, y))
            print(f"[protocol] {phase:14s} {start:7.1f} -> {frame_idx / fps:7.1f} s  y={y}")
    finally:
        cap.release()
        writer.release()
        cv2.destroyAllWindows()
        with labels_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["start_sec", "end_sec", "phase", "y"])
            w.writerows(segments)
    print(f"[protocol] wrote {video_path}\n[protocol] wrote {labels_path}")
    return labels_path


def main(argv=None):
    p = argparse.ArgumentParser(description="Record the model6 data protocol")
    p.add_argument("--participant", type=int, required=True, help="number N -> 'participant N'")
    p.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--quick", action="store_true", help="10 s per phase dry run")
    args = p.parse_args(argv)
    record(args.participant, args.raw_root, args.camera, args.quick)


if __name__ == "__main__":
    main()
