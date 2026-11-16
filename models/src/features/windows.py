"""Aggregate per-frame features into temporal windows."""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from .face_pose import FrameFeatures

WINDOW_FEATURE_NAMES: List[str] = [
    "gaze_dev_mean",
    "gaze_dev_std",
    "head_yaw_dev",
    "head_pitch_dev",
    "head_roll_dev",
    "on_screen_ratio",
    "off_screen_dwell_sec",
    "glance_count",
    "blink_rate",
    "perclos",
    "face_present_ratio",
    "body_motion_energy",
    "hand_to_face_ratio",
    "talking_score",
]

# Ablation candidates (decided by data during training).
ABLATION_CANDIDATES = ("blink_rate", "perclos", "talking_score", "body_motion_energy")


def _on_screen(f: FrameFeatures, yaw0: float, pitch0: float) -> bool:
    """Screen-looking proxy: small head deviation + iris near centre. Face required."""
    if not f.face_present:
        return False
    yaw_dev = abs(f.yaw - yaw0)
    pitch_dev = abs(f.pitch - pitch0)
    iris_dev = abs(f.iris_x - 0.5) + abs(f.iris_y - 0.5)
    return yaw_dev < 18.0 and pitch_dev < 18.0 and iris_dev < 0.35


def compute_pose_baseline(
    frames: Sequence[FrameFeatures], n_frames: int = 30
) -> Tuple[float, float, float]:
    """Median yaw/pitch/roll of the first N face-present frames (live baseline)."""
    samples = [
        (f.yaw, f.pitch, f.roll) for f in frames if f.face_present
    ][: max(1, n_frames)]
    if not samples:
        return 0.0, 0.0, 0.0
    yaw0 = float(np.median([s[0] for s in samples]))
    pitch0 = float(np.median([s[1] for s in samples]))
    roll0 = float(np.median([s[2] for s in samples]))
    return yaw0, pitch0, roll0


def windows_from_frames(
    frames: Sequence[FrameFeatures],
    window_sec: float,
    hop_sec: float = 1.0,
    yaw0: Optional[float] = None,
    pitch0: Optional[float] = None,
    roll0: Optional[float] = None,
    baseline_frames: int = 30,
) -> List[dict]:
    if not frames:
        return []
    if yaw0 is None or pitch0 is None or roll0 is None:
        yb, pb, rb = compute_pose_baseline(frames, baseline_frames)
        yaw0 = yb if yaw0 is None else yaw0
        pitch0 = pb if pitch0 is None else pitch0
        roll0 = rb if roll0 is None else roll0

    t0 = frames[0].t_sec
    t1 = frames[-1].t_sec
    rows: List[dict] = []
    start = t0
    while start + window_sec <= t1 + 1e-6:
        end = start + window_sec
        win = [f for f in frames if start - 1e-6 <= f.t_sec < end + 1e-6]
        if len(win) < min_window_frames(window_sec):
            start += hop_sec
            continue
        rows.append(
            aggregate_window(win, window_sec, yaw0, pitch0, start=start, roll0=roll0)
        )
        start += hop_sec
    return rows


def min_window_frames(window_sec: float) -> int:
    return max(2, int(window_sec))


def aggregate_window(
    win: Sequence[FrameFeatures],
    window_sec: float,
    yaw0: float,
    pitch0: float,
    start: Optional[float] = None,
    roll0: float = 0.0,
    on_screen_fn: Optional[Callable[[FrameFeatures, float, float], bool]] = None,
) -> dict:
    """Window features from per-frame features.

    Shared by offline extraction and the live backend scorer
    (models/src/features/live.py) so both compute the same 14 features.

    ``on_screen_fn(frame, yaw0, pitch0) -> bool`` decides per face frame whether
    the gaze is on screen. Default = ``_on_screen`` so training / thesis
    extraction is unchanged; the live scorer passes the screen-gaze mapper.
    """
    if on_screen_fn is None:
        on_screen_fn = _on_screen
    face_win = [f for f in win if f.face_present]
    face_flags = np.array([f.face_present for f in win], dtype=bool)

    if face_win:
        yaw_devs = np.array([abs(f.yaw - yaw0) for f in face_win], dtype=np.float64)
        pitch_devs = np.array([abs(f.pitch - pitch0) for f in face_win], dtype=np.float64)
        roll_devs = np.array([abs(f.roll - roll0) for f in face_win], dtype=np.float64)
        iris_devs = np.array(
            [abs(f.iris_x - 0.5) + abs(f.iris_y - 0.5) for f in face_win], dtype=np.float64
        )
        gaze_dev = 0.5 * (yaw_devs / 45.0) + 0.5 * iris_devs
        on_flags = np.array(
            [bool(on_screen_fn(f, yaw0, pitch0)) for f in face_win], dtype=bool
        )
        times = np.array([f.t_sec for f in face_win], dtype=np.float64)
    else:
        yaw_devs = pitch_devs = roll_devs = gaze_dev = np.zeros(0, dtype=np.float64)
        on_flags = np.zeros(0, dtype=bool)
        times = np.zeros(0, dtype=np.float64)

    blinks = np.array([f.blink for f in win], dtype=np.float64)
    jaws = np.array([f.jaw_open for f in win], dtype=np.float64)
    motions = np.array([f.body_motion for f in win], dtype=np.float64)

    # Off-screen dwell from real timestamps on face-present frames only.
    dwell = 0.0
    if len(face_win) >= 1:
        longest = cur = 0.0
        for i, on in enumerate(on_flags):
            if not on:
                if i + 1 < len(times):
                    dt = float(times[i + 1] - times[i])
                elif i > 0:
                    dt = float(times[i] - times[i - 1])
                else:
                    dt = window_sec / max(len(win), 1)
                cur += max(dt, 0.0)
                longest = max(longest, cur)
            else:
                cur = 0.0
        dwell = longest

    # Glance count: short off bursts (<2 s) between on-screen face frames
    glances = 0
    if len(on_flags):
        i = 0
        while i < len(on_flags):
            if not on_flags[i]:
                j = i
                while j < len(on_flags) and not on_flags[j]:
                    j += 1
                if j < len(on_flags):
                    off_sec = float(times[j] - times[i]) if j < len(times) else 0.0
                    if off_sec < 2.0:
                        glances += 1
                i = j
            else:
                i += 1

    perclos = float(np.mean(blinks > 0.5)) if len(blinks) else 0.0
    # Hand near face only when body is present (avoids missing-pose false near).
    hand_flags = [
        (f.hand_to_face < 0.25) and f.body_present for f in win
    ]
    hand_near = float(np.mean(hand_flags)) if hand_flags else 0.0

    on_ratio = float(np.mean(on_flags)) if len(on_flags) else 0.0

    return {
        "window_start_sec": float(win[0].t_sec if start is None else start),
        "window_sec": float(window_sec),
        "yaw0": float(yaw0),
        "pitch0": float(pitch0),
        "roll0": float(roll0),
        "gaze_dev_mean": float(np.mean(gaze_dev)) if len(gaze_dev) else 0.0,
        "gaze_dev_std": float(np.std(gaze_dev)) if len(gaze_dev) else 0.0,
        "head_yaw_dev": float(np.mean(yaw_devs)) if len(yaw_devs) else 0.0,
        "head_pitch_dev": float(np.mean(pitch_devs)) if len(pitch_devs) else 0.0,
        "head_roll_dev": float(np.mean(roll_devs)) if len(roll_devs) else 0.0,
        "on_screen_ratio": on_ratio,
        "off_screen_dwell_sec": float(dwell),
        "glance_count": float(glances),
        "blink_rate": float(np.mean(blinks)) if len(blinks) else 0.0,
        "perclos": float(perclos),
        "face_present_ratio": float(np.mean(face_flags)) if len(face_flags) else 0.0,
        "body_motion_energy": float(np.mean(motions)) if len(motions) else 0.0,
        "hand_to_face_ratio": float(hand_near),
        "talking_score": float(np.std(jaws) + np.mean(jaws)) if len(jaws) else 0.0,
        # Not a model feature: used by the live body-without-face rule.
        "body_present_ratio": float(np.mean([f.body_present for f in win])),
    }


def distraction_proxy(row: dict) -> float:
    """Higher = more distracted. Combines head-away, dwell, hands, motion."""
    on_ratio = float(row["on_screen_ratio"])
    dwell = float(row["off_screen_dwell_sec"])
    hand = float(row.get("hand_to_face_ratio", 0.0))
    motion = float(row.get("body_motion_energy", 0.0))
    gaze = float(row.get("gaze_dev_mean", 0.0))
    yaw = float(row.get("head_yaw_dev", 0.0)) / 45.0
    pitch = float(row.get("head_pitch_dev", 0.0)) / 45.0
    return (
        (1.0 - on_ratio)
        + 0.25 * min(dwell / 5.0, 1.0)
        + 0.35 * hand
        + 0.25 * min(motion * 20.0, 1.0)
        + 0.25 * gaze
        + 0.15 * min(yaw + pitch, 1.0)
    )


def label_window_row(condition: str, row: dict) -> Optional[int]:
    """
    Auto-label for forced/focused vs distracted. Returns 0/1 or None to drop.
    natural → always None (held out for false-alarm scoring).

    WARNING — circular: these labels are rules over the same window features
    the model consumes, so a model trained on them can only learn this rule.
    Kept for reproducing the v2 results (``extract --labels rule``); new
    training data uses human distraction_spans labels.
    """
    cond = condition.lower().strip()
    on_ratio = float(row["on_screen_ratio"])
    dwell = float(row["off_screen_dwell_sec"])
    face = float(row["face_present_ratio"])
    proxy = distraction_proxy(row)

    if cond == "natural":
        return None

    if cond in ("focused", "forced"):
        if face < 0.5:
            return None
        if on_ratio >= 0.70 and dwell < 2.0 and proxy < 0.55:
            return 0
        return None

    if cond == "distracted":
        if dwell >= 2.0 or on_ratio <= 0.40:
            return 1
        if float(row.get("hand_to_face_ratio", 0.0)) >= 0.35:
            return 1
        if proxy >= 0.55:
            return 1
        return None

    return None


def relabel_dataframe(df):
    """Recompute y / in_train from condition + features (no re-extract)."""
    ys = []
    for _, row in df.iterrows():
        y = label_window_row(str(row["condition"]), row.to_dict())
        ys.append(-1 if y is None else int(y))
    out = df.copy()
    out["y"] = ys
    out["in_train"] = (out["y"] >= 0).astype(int)

    for sid in out["subject_id"].unique():
        m_foc = (
            (out["subject_id"] == sid)
            & (out["condition"].isin(["focused", "forced"]))
            & (out["y"] == 0)
        )
        m_dist = (out["subject_id"] == sid) & (out["condition"] == "distracted")
        foc = out[m_foc]
        dist = out[m_dist]
        if foc.empty or dist.empty:
            continue
        foc_scores = foc.apply(distraction_proxy, axis=1)
        thr = float(foc_scores.quantile(0.90))
        dist_scores = dist.apply(distraction_proxy, axis=1)
        take = dist_scores >= thr
        idx = dist.index[take]
        before = int((m_dist & (out["y"] == 1)).sum())
        out.loc[idx, "y"] = 1
        out.loc[idx, "in_train"] = 1
        drop = dist_scores < float(foc_scores.median())
        drop_idx = dist.index[drop & ~take]
        out.loc[drop_idx, "y"] = -1
        out.loc[drop_idx, "in_train"] = 0
        after = int(((out["subject_id"] == sid) & (out["y"] == 1)).sum())
        print(
            f"[relabel] {sid}: focused_p90={thr:.3f} "
            f"distracted positives {before}→{after}"
        )
    return out
