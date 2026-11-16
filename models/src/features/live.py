"""Live per-session window scorer — the online twin of extract.extract_clip.

PLAN 4: calibration_frames lock the baseline; rolling EMA re-baseline from
confidently-focused frames; roll included in the pose baseline.

PLAN 5 Step 1: optional screen-mapped gaze. A 5-dot look calibration (frames
carrying ``calib_target``) fits a :class:`ScreenGazeMapper`; the centre dot
locks the head baseline. If the fit fails (or calibration is skipped) a
baseline-centred rule is used instead. With ``screen_gaze=False`` (default)
the scorer uses the training-time ``_on_screen`` proxy, so offline/live
feature parity is unchanged.
"""

from __future__ import annotations

import os
from collections import deque
from typing import Deque, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from .face_pose import FrameFeatureExtractor, FrameFeatures
from .screen_gaze import BLINK_THRESHOLD, ScreenGazeMapper, is_blink
from .windows import _on_screen, aggregate_window, min_window_frames

Baseline = Tuple[float, float, float]  # yaw, pitch, roll
CalibTarget = Union[Sequence[float], Dict[str, float]]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def _norm_target(t: Optional[CalibTarget]) -> Optional[Tuple[float, float]]:
    if t is None:
        return None
    try:
        if isinstance(t, dict):
            x, y = float(t["x"]), float(t["y"])
        else:
            x, y = float(t[0]), float(t[1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if not (np.isfinite(x) and np.isfinite(y)):
        return None
    return x, y


class LiveWindowScorer:
    def __init__(
        self,
        window_sec: float = 5.0,
        baseline_frames: int = 30,
        calibration_frames: Optional[int] = None,
        extractor: Optional[FrameFeatureExtractor] = None,
        rebaseline_alpha: float = 0.02,
        rebaseline_max_drift_deg: float = 10.0,
        screen_gaze: bool = False,
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

        # --- PLAN 5 screen gaze --------------------------------------------
        self.screen_gaze = bool(screen_gaze)
        self._mapper = ScreenGazeMapper()
        self._calib_active = False
        # (yaw, pitch, iris_x, iris_y, sx, sy, roll)
        self._calib_samples: List[Tuple[float, ...]] = []
        self._calib_has_head_phase: bool = False
        self._iris_samples: List[Tuple[float, float]] = []
        self._iris0: Optional[Tuple[float, float]] = None
        self._screen: Optional[dict] = None
        self._calib_status: dict = {}
        self.fb_iris_x = _env_float("ML_GAZE_FB_IRIS_X", 0.08)
        self.fb_iris_y = _env_float("ML_GAZE_FB_IRIS_Y", 0.10)
        self.fb_yaw_deg = _env_float("ML_GAZE_FB_YAW_DEG", 12.0)
        self.fb_pitch_deg = _env_float("ML_GAZE_FB_PITCH_DEG", 12.0)

    # ------------------------------------------------------------ baseline

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

    @property
    def mapper(self) -> ScreenGazeMapper:
        return self._mapper

    @property
    def gaze_mode(self) -> str:
        """"screen" (fitted mapper) | "fallback" (baseline-centred) | "legacy"."""
        if not self.screen_gaze:
            return "legacy"
        return "screen" if self._mapper.ok else "fallback"

    def set_calibrating(self, on: bool) -> None:
        self._calibrating = bool(on)

    def reset(self) -> None:
        self._frames.clear()
        self._baseline_samples.clear()
        self._yaw0 = self._pitch0 = self._roll0 = 0.0
        self._baseline_locked = False
        self._last_t = None
        self._iris_samples.clear()
        self._iris0 = None
        self._mapper.reset_history()

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

    # --------------------------------------------------------- calibration

    def set_screen(self, screen: Optional[dict]) -> None:
        """Remember the client's display geometry {w, h, inner_w, inner_h, dpr}."""
        if not screen:
            return
        clean = {}
        for k in ("w", "h", "inner_w", "inner_h", "dpr"):
            try:
                v = float(screen[k])
            except (KeyError, TypeError, ValueError):
                continue
            if np.isfinite(v):
                clean[k] = v
        self._screen = clean or None

    @property
    def screen(self) -> Optional[dict]:
        return self._screen

    def start_calibration(self) -> None:
        """Begin a (re)calibration: forget the old mapper and head baseline."""
        self._calib_samples = []
        self._calib_has_head_phase = False
        self._mapper = ScreenGazeMapper()
        self._baseline_samples.clear()
        self._baseline_locked = False
        self._yaw0 = self._pitch0 = self._roll0 = 0.0
        self._iris_samples.clear()
        self._iris0 = None
        self._calib_active = True
        self._calibrating = True
        self._calib_status = {"phase": "collect", "ok": None}

    def add_calibration_sample(
        self, f: FrameFeatures, target: Optional[CalibTarget]
    ) -> bool:
        """Record one frame looked at normalised screen point ``target``.

        Frames without a face or a real blink are rejected. Looking-down with
        lowered lids is kept. Returns True if kept.
        """
        tgt = _norm_target(target)
        if tgt is None or f is None or not f.face_present:
            return False
        if is_blink(f):
            return False
        # Head phase: many centre-target samples with head motion (yaw variance).
        if abs(tgt[0] - 0.5) < 0.05 and abs(tgt[1] - 0.5) < 0.05:
            # Mark head phase once we already have star samples and head is moving.
            if len(self._calib_samples) >= 20:
                recent = self._calib_samples[-15:]
                yaws = [s[0] for s in recent]
                if max(yaws) - min(yaws) > 4.0:
                    self._calib_has_head_phase = True
        self._calib_samples.append(
            (
                float(f.yaw),
                float(f.pitch),
                float(f.iris_x),
                float(f.iris_y),
                tgt[0],
                tgt[1],
                float(getattr(f, "look_h", 0.0) or 0.0),
                float(getattr(f, "look_v", 0.0) or 0.0),
                float(f.roll),
            )
        )
        return True

    def finish_calibration(self) -> dict:
        """Fit the mapper and lock head/iris baseline from the centre dot."""
        self._calib_active = False
        self._calibrating = False
        samples = list(self._calib_samples)
        mapper = ScreenGazeMapper()
        # Samples: yaw, pitch, ix, iy, sx, sy, look_h, look_v[, roll]
        fit_rows = [s[:8] for s in samples]
        ok = mapper.fit(fit_rows, has_head_phase=bool(self._calib_has_head_phase))
        self._mapper = mapper

        centre_locked = False
        groups: Dict[Tuple[float, float], list] = {}
        for s in samples:
            groups.setdefault((round(s[4], 3), round(s[5], 3)), []).append(s)
        eligible = [
            (k, v) for k, v in groups.items() if len(v) >= mapper.min_samples_per_dot
        ]
        if eligible:
            k, v = min(eligible, key=lambda kv: (kv[0][0] - 0.5) ** 2 + (kv[0][1] - 0.5) ** 2)
            if (k[0] - 0.5) ** 2 + (k[1] - 0.5) ** 2 <= 0.15 ** 2:
                arr = np.asarray(v, dtype=np.float64)
                self._yaw0 = float(np.median(arr[:, 0]))
                self._pitch0 = float(np.median(arr[:, 1]))
                # roll is last column when present
                roll_col = arr[:, -1] if arr.shape[1] >= 9 else arr[:, 0] * 0.0
                self._roll0 = float(np.median(roll_col))
                self._iris0 = (float(np.median(arr[:, 2])), float(np.median(arr[:, 3])))
                self._baseline_locked = True
                centre_locked = True
        self._calib_status = {
            "phase": "finish",
            "ok": bool(ok),
            "residual": mapper.to_dict()["residual"],
            "n_dots": int(mapper.n_dots),
            "n_samples": len(samples),
            "centre_locked": centre_locked,
            "fallback": not ok,
            "head_phase": bool(self._calib_has_head_phase),
            "freeze_head": bool(mapper.freeze_head),
        }
        return dict(self._calib_status)

    def calibration_status(self) -> dict:
        st = dict(self._calib_status)
        st.update(
            {
                "active": bool(self._calib_active),
                "mapped": bool(self._mapper.ok),
                "mode": self.gaze_mode,
                "baseline_locked": bool(self._baseline_locked),
                "n_samples": len(self._calib_samples),
            }
        )
        return st

    def export_calibration(self) -> Optional[dict]:
        """Persistable fit + centre baseline. None when the mapper is not fitted."""
        mapper_state = self._mapper.export_state()
        if mapper_state is None:
            return None
        iris0 = None
        if self._iris0 is not None:
            iris0 = [float(self._iris0[0]), float(self._iris0[1])]
        return {
            "mapper": mapper_state,
            "yaw0": float(self._yaw0),
            "pitch0": float(self._pitch0),
            "roll0": float(self._roll0),
            "iris0": iris0,
            "baseline_locked": bool(self._baseline_locked),
            "head_phase": bool(self._calib_has_head_phase),
            "freeze_head": bool(self._mapper.freeze_head),
            "screen": dict(self._screen) if self._screen else None,
        }

    def restore_calibration(self, payload: Optional[dict]) -> bool:
        """Load a previously exported fit. Returns True when the mapper is ready."""
        if not payload or not isinstance(payload, dict):
            return False
        mapper_state = payload.get("mapper")
        if not isinstance(mapper_state, dict):
            # Allow a flat export that is already the mapper state (cx/cy present).
            mapper_state = payload if "cx" in payload and "cy" in payload else None
        if not mapper_state:
            return False
        mapper = ScreenGazeMapper()
        if payload.get("margin") is not None and "margin" not in mapper_state:
            mapper_state = {**mapper_state, "margin": payload["margin"]}
        if not mapper.load_state(mapper_state):
            return False
        self._mapper = mapper
        self._calib_active = False
        self._calibrating = False
        self._calib_samples = []
        self._calib_has_head_phase = bool(payload.get("head_phase", not mapper.freeze_head))
        try:
            self._yaw0 = float(payload.get("yaw0", 0.0) or 0.0)
            self._pitch0 = float(payload.get("pitch0", 0.0) or 0.0)
            self._roll0 = float(payload.get("roll0", 0.0) or 0.0)
        except (TypeError, ValueError):
            self._yaw0 = self._pitch0 = self._roll0 = 0.0
        iris0 = payload.get("iris0")
        if isinstance(iris0, (list, tuple)) and len(iris0) >= 2:
            try:
                self._iris0 = (float(iris0[0]), float(iris0[1]))
            except (TypeError, ValueError):
                self._iris0 = None
        else:
            self._iris0 = None
        self._baseline_locked = bool(
            payload.get("baseline_locked", True) or self._iris0 is not None
        )
        if payload.get("screen"):
            self.set_screen(payload["screen"])
        self._calib_status = {
            "phase": "restored",
            "ok": True,
            "residual": mapper.to_dict()["residual"],
            "n_dots": int(mapper.n_dots),
            "centre_locked": self._baseline_locked,
            "fallback": False,
            "head_phase": bool(self._calib_has_head_phase),
            "freeze_head": bool(mapper.freeze_head),
            "restored": True,
        }
        return True

    # -------------------------------------------------------------- on-screen

    def _fallback_on_screen(self, f: FrameFeatures, yaw0: float, pitch0: float) -> bool:
        """Baseline-centred rule used when no screen mapping is available."""
        if abs(f.yaw - yaw0) > self.fb_yaw_deg or abs(f.pitch - pitch0) > self.fb_pitch_deg:
            return False
        # Real blinks are neutral (inherit on-screen); looking-down is evaluated.
        if is_blink(f):
            return True
        if self._iris0 is not None:
            if abs(f.iris_x - self._iris0[0]) > self.fb_iris_x:
                return False
            if abs(f.iris_y - self._iris0[1]) > self.fb_iris_y:
                return False
        # Eye-look blendshapes: strong look away without iris baseline yet.
        lh = float(getattr(f, "look_h", 0.0) or 0.0)
        lv = float(getattr(f, "look_v", 0.0) or 0.0)
        if abs(lh) > 0.35 or abs(lv) > 0.35:
            return False
        return True

    def _on_screen_face(self, f: FrameFeatures, yaw0: float, pitch0: float) -> bool:
        """``on_screen_fn`` for aggregate_window (face-present frames)."""
        if not self.screen_gaze:
            return _on_screen(f, yaw0, pitch0)
        if not f.face_present:
            return False
        # PLAN 8: without a head phase the mapper freezes head weights — still
        # treat large head deviation as off-screen.
        if abs(f.yaw - yaw0) > self.fb_yaw_deg or abs(f.pitch - pitch0) > self.fb_pitch_deg:
            if getattr(self._mapper, "freeze_head", False) or not self._mapper.ok:
                return False
        if self._mapper.ok:
            return self._mapper.is_on_screen(f)
        if self._iris0 is None:
            return _on_screen(f, yaw0, pitch0)
        return self._fallback_on_screen(f, yaw0, pitch0)

    def _gaze_state(self, f: FrameFeatures) -> Optional[bool]:
        """True on-screen / False off-screen / None neutral."""
        if f.face_present:
            return self._on_screen_face(f, self._yaw0, self._pitch0)
        # No face: a body in view means the child turned/looked away hard.
        return False if f.body_present else None

    def frame_debug(self, f: FrameFeatures) -> dict:
        """Compact per-frame record for the evaluation terminal (PLAN 7/8)."""
        on = self._gaze_state(f)
        out = {
            "t": round(float(f.t_sec), 3),
            "face": bool(f.face_present),
            "body": bool(getattr(f, "body_present", False)),
            "on_screen": on,
            "yaw_dev": None,
            "pitch_dev": None,
            "sx": None,
            "sy": None,
            "blink": round(float(f.blink), 2),
            "look_h": round(float(getattr(f, "look_h", 0.0) or 0.0), 3),
            "look_v": round(float(getattr(f, "look_v", 0.0) or 0.0), 3),
            "look_down": round(float(getattr(f, "look_down", 0.0) or 0.0), 3),
        }
        if f.face_present:
            out["yaw_dev"] = round(float(f.yaw - (self._yaw0 or 0.0)), 1)
            out["pitch_dev"] = round(float(f.pitch - (self._pitch0 or 0.0)), 1)
            if self._mapper.ok:
                try:
                    p = self._mapper.predict(f)
                except Exception:
                    p = None
                if p is not None:
                    out["sx"], out["sy"] = round(float(p[0]), 3), round(float(p[1]), 3)
        return out

    def gaze_summary(self, recent_sec: float = 3.0) -> dict:
        """Current gaze vs screen: position, dwell and off-ratio over recent frames."""
        out = {
            "mode": self.gaze_mode,
            "calibrated": bool(self._mapper.ok),
            "sx": None,
            "sy": None,
            "on_screen": None,
            "off_dwell_sec": 0.0,
            "on_dwell_sec": 0.0,
            "off_ratio": 0.0,
        }
        if not self._frames:
            return out
        latest = self._frames[-1]
        t_latest = float(latest.t_sec)
        states = [(float(f.t_sec), self._gaze_state(f)) for f in self._frames]
        valid = [(t, s) for t, s in states if s is not None]
        if latest.face_present and self._mapper.ok:
            p = self._mapper.predict(latest)
            if p is not None:
                out["sx"], out["sy"] = round(float(p[0]), 4), round(float(p[1]), 4)
        if not valid:
            return out
        cur = valid[-1][1]
        out["on_screen"] = bool(cur)
        # Continuous run of the current state, walking back from the newest frame.
        run_start = valid[-1][0]
        for t, s in reversed(valid):
            if s != cur:
                break
            run_start = t
        dwell = max(t_latest - run_start, 0.0)
        out["off_dwell_sec" if not cur else "on_dwell_sec"] = round(dwell, 3)
        recent = [s for t, s in valid if t >= t_latest - recent_sec - 1e-6]
        if recent:
            out["off_ratio"] = round(float(np.mean([not s for s in recent])), 4)
        return out

    def maybe_rebaseline(self, dist_prob: float, face_present: bool) -> None:
        """Slow EMA toward current pose when confidently focused (and on-screen)."""
        if not self._baseline_locked or not face_present or dist_prob >= 0.2:
            return
        if not self._frames:
            return
        f = self._frames[-1]
        if not f.face_present:
            return
        # PLAN 5: head baseline only drifts while gaze is on-screen, otherwise a
        # sustained look-away would be absorbed into the baseline.
        if self.screen_gaze and self._gaze_state(f) is not True:
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

    # --------------------------------------------------------------- frames

    def add_frame(
        self,
        t_sec: float,
        frame_bgr: np.ndarray,
        calib_target: Optional[CalibTarget] = None,
    ) -> Optional[FrameFeatures]:
        """Process one frame. Frames not newer than the last one are ignored."""
        if self._last_t is not None and t_sec < self._last_t - 1e-6:
            # Client clock went backwards — reset temporal state
            self.reset()
        if self._last_t is not None and t_sec <= self._last_t:
            return None
        self._last_t = float(t_sec)
        f = self._extractor.process(frame_bgr, float(t_sec))
        self._frames.append(f)
        if self._mapper.ok:
            self._mapper.observe(f)

        tgt = _norm_target(calib_target)
        if tgt is not None:
            # Calibration dot frames feed the mapper / centre baseline only.
            self.add_calibration_sample(f, tgt)
        elif f.face_present and not self._baseline_locked:
            # Baseline is collected while calibrating (no-dot lead-in frames) or,
            # failing that, until locked from the first face frames. Once the
            # centre dot (or enough frames) locks it, collection stops.
            self._baseline_samples.append((f.yaw, f.pitch, f.roll))
            self._lock_baseline_if_ready()
        if (
            tgt is None
            and f.face_present
            and self._iris0 is None
            and not is_blink(f)
        ):
            self._iris_samples.append((float(f.iris_x), float(f.iris_y)))
            if len(self._iris_samples) >= 10:
                self._iris0 = (
                    float(np.median([s[0] for s in self._iris_samples])),
                    float(np.median([s[1] for s in self._iris_samples])),
                )
        keep = max(self.window_sec + 1.0, 4.5)
        while self._frames and self._frames[0].t_sec < t_sec - keep:
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
            win,
            self.window_sec,
            yaw0,
            pitch0,
            start=start,
            roll0=roll0,
            on_screen_fn=self._on_screen_face,
        )
        out["baseline_locked"] = self.baseline_locked
        out["calibrating"] = bool(self._calibrating) and not self.baseline_locked
        out["n_frames"] = len(win)
        out["window_end_sec"] = float(latest)
        out["gaze"] = self.gaze_summary()
        return out

    def close(self) -> None:
        self._extractor.close()
