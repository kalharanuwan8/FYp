"""Aggregate per-frame features into temporal windows."""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .face_pose import FrameFeatures

WINDOW_FEATURE_NAMES: List[str] = [
    "gaze_dev_mean",
    "gaze_dev_std",
    "head_yaw_dev",
    "head_pitch_dev",
    "head_roll_mean",
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


def _on_screen(f: FrameFeatures, yaw0: float, pitch0: float) -> bool:
    """Screen-looking proxy: small head deviation + iris near centre."""
    yaw_dev = abs(f.yaw - yaw0)
    pitch_dev = abs(f.pitch - pitch0)
    iris_dev = abs(f.iris_x - 0.5) + abs(f.iris_y - 0.5)
    if not f.face_present:
        return False
    return yaw_dev < 18.0 and pitch_dev < 18.0 and iris_dev < 0.35


def compute_pose_baseline(
    frames: Sequence[FrameFeatures], n_frames: int = 30
) -> Tuple[float, float]:
    """Median yaw/pitch of the first N face-present frames (live _centered_pose_buf)."""
    samples = [(f.yaw, f.pitch) for f in frames if f.face_present][: max(1, n_frames)]
    if not samples:
        return 0.0, 0.0
    yaw0 = float(np.median([s[0] for s in samples]))
    pitch0 = float(np.median([s[1] for s in samples]))
    return yaw0, pitch0


def windows_from_frames(
    frames: Sequence[FrameFeatures],
    window_sec: float,
    hop_sec: float = 1.0,
    yaw0: Optional[float] = None,
    pitch0: Optional[float] = None,
    baseline_frames: int = 30,
) -> List[dict]:
    if not frames:
        return []
    if yaw0 is None or pitch0 is None:
        yb, pb = compute_pose_baseline(frames, baseline_frames)
        yaw0 = yb if yaw0 is None else yaw0
        pitch0 = pb if pitch0 is None else pitch0

    t0 = frames[0].t_sec
    t1 = frames[-1].t_sec
    rows: List[dict] = []
    start = t0
    while start + window_sec <= t1 + 1e-6:
        end = start + window_sec
        win = [f for f in frames if start - 1e-6 <= f.t_sec < end + 1e-6]
        if len(win) < max(2, int(window_sec)):  # need a few samples
            start += hop_sec
            continue

        yaw_devs = np.array([abs(f.yaw - yaw0) for f in win], dtype=np.float64)
        pitch_devs = np.array([abs(f.pitch - pitch0) for f in win], dtype=np.float64)
        iris_devs = np.array(
            [abs(f.iris_x - 0.5) + abs(f.iris_y - 0.5) for f in win], dtype=np.float64
        )
        gaze_dev = 0.5 * (yaw_devs / 45.0) + 0.5 * iris_devs
        on_flags = np.array([_on_screen(f, yaw0, pitch0) for f in win], dtype=bool)
        face_flags = np.array([f.face_present for f in win], dtype=bool)
        blinks = np.array([f.blink for f in win], dtype=np.float64)
        jaws = np.array([f.jaw_open for f in win], dtype=np.float64)
        motions = np.array([f.body_motion for f in win], dtype=np.float64)
        hands = np.array([f.hand_to_face for f in win], dtype=np.float64)

        # Off-screen dwell: longest consecutive off-screen run in seconds
        dt = window_sec / max(len(win), 1)
        longest = cur = 0
        for on in on_flags:
            if not on:
                cur += 1
                longest = max(longest, cur)
            else:
                cur = 0
        dwell = longest * dt

        # Glance count: off→on transitions with short off bursts (<2 s)
        glances = 0
        i = 0
        while i < len(on_flags):
            if not on_flags[i]:
                j = i
                while j < len(on_flags) and not on_flags[j]:
                    j += 1
                off_sec = (j - i) * dt
                if off_sec < 2.0 and j < len(on_flags):
                    glances += 1
                i = j
            else:
                i += 1

        perclos = float(np.mean(blinks > 0.5)) if len(blinks) else 0.0
        # Hand near face: distance threshold ~0.25 of frame diagonal-ish (norm coords)
        hand_near = float(np.mean(hands < 0.25)) if len(hands) else 0.0

        rows.append(
            {
                "window_start_sec": float(start),
                "window_sec": float(window_sec),
                "yaw0": float(yaw0),
                "pitch0": float(pitch0),
                "gaze_dev_mean": float(np.mean(gaze_dev)),
                "gaze_dev_std": float(np.std(gaze_dev)),
                "head_yaw_dev": float(np.mean(yaw_devs)),
                "head_pitch_dev": float(np.mean(pitch_devs)),
                "head_roll_mean": float(np.mean([f.roll for f in win])),
                "on_screen_ratio": float(np.mean(on_flags)),
                "off_screen_dwell_sec": float(dwell),
                "glance_count": float(glances),
                "blink_rate": float(np.mean(blinks)),
                "perclos": float(perclos),
                "face_present_ratio": float(np.mean(face_flags)),
                "body_motion_energy": float(np.mean(motions)),
                "hand_to_face_ratio": float(hand_near),
                "talking_score": float(np.std(jaws) + np.mean(jaws)),
            }
        )
        start += hop_sec
    return rows


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
    """
    cond = condition.lower().strip()
    on_ratio = float(row["on_screen_ratio"])
    dwell = float(row["off_screen_dwell_sec"])
    face = float(row["face_present_ratio"])
    proxy = distraction_proxy(row)

    if cond == "natural":
        return None

    if cond in ("focused", "forced"):
        # Keep only clearly on-task windows
        if face < 0.5:
            return None
        if on_ratio >= 0.70 and dwell < 2.0 and proxy < 0.55:
            return 0
        return None

    if cond == "distracted":
        # Head-away episodes
        if dwell >= 2.0 or on_ratio <= 0.40:
            return 1
        # Phone / fidget while still facing camera (common in these clips)
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

    # Subject-calibrated distracted labels: positive if proxy exceeds the
    # focused-clip 90th percentile (captures phone distraction while facing cam).
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
        # Keep existing head-away positives; add calibrated ones
        idx = dist.index[take]
        before = int((m_dist & (out["y"] == 1)).sum())
        out.loc[idx, "y"] = 1
        out.loc[idx, "in_train"] = 1
        # Drop distracted windows clearly below focused median (on-task returns)
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
