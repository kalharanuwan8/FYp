"""Live per-session window scorer — the online twin of extract.extract_clip.

PLAN 4: calibration_frames lock the baseline; rolling EMA re-baseline from
confidently-focused frames; roll included in the pose baseline.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional, Tuple

import numpy as np

from .face_pose import FrameFeatureExtractor, FrameFeatures
from .windows import aggregate_window, min_window_frames

Baseline = Tuple[float, float, float]  # yaw, pitch, roll


class LiveWindowScorer:
    def __init__(
        self,
        window_sec: float = 5.0,
        baseline_frames: int = 30,
        calibration_frames: Optional[int] = None,
        extractor: Optional[FrameFeatureExtractor] = None,
        rebaseline_alpha: float = 0.02,
        rebaseline_max_drift_deg: float = 10.0,
    ):
        self.window_sec = float(window_sec)
        self.baseline_frames = int(
            calibration_frames if calibration_frames is not None else baseline_frames
        )
        self._extractor = extractor or FrameFeatureExtractor()
        self._frames: Deque[FrameFeatures] = deque()
        self._baseline_samples: List[Baseline] = []
        self._yaw0 = self._pitch0 = self._roll0 = 0.0
        self._baseline_locked = False
        self._last_t: Optional[float] = None
        self._rebaseline_alpha = float(rebaseline_alpha)
        self._rebaseline_max_drift = float(rebaseline_max_drift_deg)
        self._calibrating = False

    @property
    def baseline(self) -> Baseline:
        if not self._baseline_locked and self._baseline_samples:
            return (
                float(np.median([s[0] for s in self._baseline_samples])),
                float(np.median([s[1] for s in self._baseline_samples])),
                float(np.median([s[2] for s in self._baseline_samples])),
            )
        return self._yaw0, self._pitch0, self._roll0

    @property
    def baseline_locked(self) -> bool:
        return self._baseline_locked

    def set_calibrating(self, on: bool) -> None:
        self._calibrating = bool(on)

    def reset(self) -> None:
        self._frames.clear()
        self._baseline_samples.clear()
        self._yaw0 = self._pitch0 = self._roll0 = 0.0
        self._baseline_locked = False
        self._last_t = None

    def _lock_baseline_if_ready(self) -> None:
        if self._baseline_locked:
            return
        if len(self._baseline_samples) >= self.baseline_frames:
            self._yaw0, self._pitch0, self._roll0 = (
                float(np.median([s[0] for s in self._baseline_samples])),
                float(np.median([s[1] for s in self._baseline_samples])),
                float(np.median([s[2] for s in self._baseline_samples])),
            )
            self._baseline_locked = True

    def maybe_rebaseline(self, dist_prob: float, face_present: bool) -> None:
        """Slow EMA toward current pose when confidently focused."""
        if not self._baseline_locked or not face_present or dist_prob >= 0.2:
            return
        if not self._frames:
            return
        f = self._frames[-1]
        if not f.face_present:
            return
        a = self._rebaseline_alpha
        for attr, val, cur in (
            ("_yaw0", f.yaw, self._yaw0),
            ("_pitch0", f.pitch, self._pitch0),
            ("_roll0", f.roll, self._roll0),
        ):
            nxt = (1 - a) * cur + a * val
            lo, hi = cur - self._rebaseline_max_drift, cur + self._rebaseline_max_drift
            setattr(self, attr, float(min(hi, max(lo, nxt))))

    def add_frame(self, t_sec: float, frame_bgr: np.ndarray) -> Optional[FrameFeatures]:
        """Process one frame. Frames not newer than the last one are ignored."""
        if self._last_t is not None and t_sec < self._last_t - 1e-6:
            # Client clock went backwards — reset temporal state
            self.reset()
        if self._last_t is not None and t_sec <= self._last_t:
            return None
        self._last_t = float(t_sec)
        f = self._extractor.process(frame_bgr, float(t_sec))
        self._frames.append(f)
        if f.face_present and not self._baseline_locked:
            # During explicit calibration, or until locked from first face frames.
            if self._calibrating or True:
                self._baseline_samples.append((f.yaw, f.pitch, f.roll))
                self._lock_baseline_if_ready()
        while self._frames and self._frames[0].t_sec < t_sec - self.window_sec - 1.0:
            self._frames.popleft()
        return f

    def features(self) -> Optional[dict]:
        """Features of the window ending at the newest frame, or None if too few frames."""
        if not self._frames:
            return None
        latest = self._frames[-1].t_sec
        start = latest - self.window_sec
        win = [f for f in self._frames if start - 1e-6 <= f.t_sec < latest + 1e-6]
        if len(win) < min_window_frames(self.window_sec):
            return None
        yaw0, pitch0, roll0 = self.baseline
        out = aggregate_window(
            win, self.window_sec, yaw0, pitch0, start=start, roll0=roll0
        )
        out["baseline_locked"] = self.baseline_locked
        out["calibrating"] = bool(self._calibrating) and not self.baseline_locked
        out["n_frames"] = len(win)
        out["window_end_sec"] = float(latest)
        return out

    def close(self) -> None:
        self._extractor.close()
