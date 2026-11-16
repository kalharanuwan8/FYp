"""Screen-mapped gaze: (head, iris, eye-look) -> normalised screen (sx, sy).

PLAN 5 + PLAN 8. Calibration yields per-frame samples

    (yaw, pitch, iris_x, iris_y, sx, sy[, look_h, look_v])

We trim the 2 most extreme frames per dot and fit ridge regressions::

    sx ~ [1, yaw, iris_x, look_h]
    sy ~ [1, pitch, iris_y, look_v]

Residual is still checked on per-dot medians (MAX_RESIDUAL unchanged).
Looking down with lowered lids is NOT treated as a blink.
"""

from __future__ import annotations

import os
from collections import deque
from typing import Deque, Dict, Optional, Sequence, Tuple

import numpy as np

MIN_VALID_DOTS = 4
MAX_RESIDUAL = 0.15
BLINK_THRESHOLD = 0.5
LOOK_DOWN_BLINK_MAX = 0.4
DEFAULT_MARGIN = float(os.environ.get("ML_GAZE_MARGIN", "0.03"))
IRIS_SMOOTH_N = 3
_CACHE_MAX = 512
_TRIM_EXTREME = 2  # drop 2 most extreme frames per dot before fitting


def is_blink(frame, blink_thr: float = BLINK_THRESHOLD) -> bool:
    """True only for a real blink — looking down with lowered lids is not a blink."""
    blink = float(getattr(frame, "blink", 0.0) or 0.0)
    look_down = float(getattr(frame, "look_down", 0.0) or 0.0)
    return blink > blink_thr and look_down < LOOK_DOWN_BLINK_MAX


class ScreenGazeMapper:
    def __init__(
        self,
        ridge: float = 1e-2,
        interaction: bool = False,
        min_dots: int = MIN_VALID_DOTS,
        max_residual: float = MAX_RESIDUAL,
        min_samples_per_dot: int = 3,
        freeze_head: bool = False,
        margin: Optional[float] = None,
    ):
        self.ridge = float(ridge)
        self.interaction = bool(interaction)  # kept for API; unused in PLAN 8 design
        self.min_dots = int(min_dots)
        self.max_residual = float(max_residual)
        self.min_samples_per_dot = int(min_samples_per_dot)
        self.freeze_head = bool(freeze_head)
        self.margin = float(DEFAULT_MARGIN if margin is None else margin)
        self.ok = False
        self.residual: float = float("inf")
        self.n_dots = 0
        self._cx: Optional[np.ndarray] = None
        self._cy: Optional[np.ndarray] = None
        self._iris_hist: Deque[Tuple[float, float]] = deque(maxlen=IRIS_SMOOTH_N)
        self._cache: Dict[float, Tuple[float, float]] = {}
        self._last_pred: Optional[Tuple[float, float]] = None

    # ------------------------------------------------------------------ fit

    def _design(self, yaw, pitch, ix, iy, lh, lv):
        """Design: sx ~ [1, yaw, iris_x, look_h]; sy ~ [1, pitch, iris_y, look_v]."""
        yaw, pitch, ix, iy, lh, lv = (
            np.asarray(v, dtype=np.float64) for v in (yaw, pitch, ix, iy, lh, lv)
        )
        one = np.ones_like(yaw)
        if self.freeze_head:
            # Old client / no head phase: rely on eye terms only.
            Ax = np.stack([one, np.zeros_like(yaw), ix, lh], axis=-1)
            Ay = np.stack([one, np.zeros_like(pitch), iy, lv], axis=-1)
        else:
            Ax = np.stack([one, yaw, ix, lh], axis=-1)
            Ay = np.stack([one, pitch, iy, lv], axis=-1)
        return Ax, Ay

    @staticmethod
    def _ridge_fit(A: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
        """Ridge on standardised non-intercept columns; coefficients returned raw."""
        mu = A[:, 1:].mean(axis=0)
        sd = A[:, 1:].std(axis=0)
        sd = np.where(sd < 1e-9, 1.0, sd)
        Z = (A[:, 1:] - mu) / sd
        ym = float(y.mean())
        k = Z.shape[1]
        w = np.linalg.solve(Z.T @ Z + lam * len(y) * np.eye(k), Z.T @ (y - ym))
        raw_w = w / sd
        b0 = ym - float(mu @ raw_w)
        return np.concatenate([[b0], raw_w])

    @staticmethod
    def _pad_look(s: Sequence[float]) -> Tuple[float, ...]:
        """Normalise a sample to (yaw, pitch, ix, iy, sx, sy, look_h, look_v)."""
        vals = [float(v) for v in s]
        while len(vals) < 8:
            vals.append(0.0)
        return tuple(vals[:8])

    @staticmethod
    def _trim_group(vs: list) -> np.ndarray:
        """Drop up to 2 most extreme frames (by iris+look distance from median)."""
        arr = np.asarray(vs, dtype=np.float64)
        if len(arr) <= _TRIM_EXTREME + 1:
            return arr
        # columns: yaw, pitch, ix, iy, look_h, look_v
        med = np.median(arr, axis=0)
        dist = np.linalg.norm(arr - med, axis=1)
        keep = np.argsort(dist)[: max(1, len(arr) - _TRIM_EXTREME)]
        return arr[keep]

    def fit(self, samples: Sequence[Sequence[float]], has_head_phase: bool = True) -> bool:
        """Fit from per-frame samples. Returns (and stores) ``ok``."""
        self.ok = False
        self.residual = float("inf")
        self.n_dots = 0
        self._cx = self._cy = None
        self.freeze_head = not bool(has_head_phase)

        groups: Dict[Tuple[float, float], list] = {}
        for s in samples or []:
            if len(s) < 6:
                continue
            yaw, pitch, ix, iy, sx, sy, lh, lv = self._pad_look(s)
            if not all(np.isfinite([yaw, pitch, ix, iy, sx, sy, lh, lv])):
                continue
            key = (round(sx, 3), round(sy, 3))
            groups.setdefault(key, []).append([yaw, pitch, ix, iy, lh, lv])

        # Residual check uses per-dot medians (stable).
        med_rows = []
        fit_rows = []
        for (sx, sy), vs in groups.items():
            if len(vs) < self.min_samples_per_dot:
                continue
            trimmed = self._trim_group(vs)
            med = np.median(trimmed, axis=0)
            med_rows.append([med[0], med[1], med[2], med[3], sx, sy, med[4], med[5]])
            for row in trimmed:
                fit_rows.append([row[0], row[1], row[2], row[3], sx, sy, row[4], row[5]])

        self.n_dots = len(med_rows)
        if self.n_dots < self.min_dots or not fit_rows:
            return False

        F = np.asarray(fit_rows, dtype=np.float64)
        Ax, Ay = self._design(F[:, 0], F[:, 1], F[:, 2], F[:, 3], F[:, 6], F[:, 7])
        try:
            cx = self._ridge_fit(Ax, F[:, 4], self.ridge)
            cy = self._ridge_fit(Ay, F[:, 5], self.ridge)
        except np.linalg.LinAlgError:
            return False

        if self.freeze_head:
            # Force head coefficients to 0 (index 1).
            cx = cx.copy()
            cy = cy.copy()
            cx[1] = 0.0
            cy[1] = 0.0

        M = np.asarray(med_rows, dtype=np.float64)
        Axm, Aym = self._design(M[:, 0], M[:, 1], M[:, 2], M[:, 3], M[:, 6], M[:, 7])
        px, py = Axm @ cx, Aym @ cy
        self.residual = float(np.sqrt(np.mean((px - M[:, 4]) ** 2 + (py - M[:, 5]) ** 2)))
        self._cx, self._cy = cx, cy
        self.ok = bool(np.isfinite(self.residual) and self.residual < self.max_residual)
        return self.ok

    # -------------------------------------------------------------- predict

    def reset_history(self) -> None:
        self._iris_hist.clear()
        self._cache.clear()
        self._last_pred = None

    def _map(
        self,
        yaw: float,
        pitch: float,
        ix: float,
        iy: float,
        lh: float = 0.0,
        lv: float = 0.0,
    ) -> Tuple[float, float]:
        Ax, Ay = self._design([yaw], [pitch], [ix], [iy], [lh], [lv])
        return float(Ax[0] @ self._cx), float(Ay[0] @ self._cy)

    def _look(self, frame) -> Tuple[float, float]:
        return (
            float(getattr(frame, "look_h", 0.0) or 0.0),
            float(getattr(frame, "look_v", 0.0) or 0.0),
        )

    def observe(self, frame) -> Optional[Tuple[float, float]]:
        """Process one frame: iris median smooth + cache. Real blinks are neutral."""
        if not self.ok or not getattr(frame, "face_present", False):
            return None
        t = float(frame.t_sec)
        lh, lv = self._look(frame)
        if is_blink(frame):
            pred = self._last_pred if self._last_pred is not None else (0.5, 0.5)
        else:
            self._iris_hist.append((float(frame.iris_x), float(frame.iris_y)))
            ix = float(np.median([p[0] for p in self._iris_hist]))
            iy = float(np.median([p[1] for p in self._iris_hist]))
            pred = self._map(frame.yaw, frame.pitch, ix, iy, lh, lv)
            self._last_pred = pred
        self._cache[t] = pred
        if len(self._cache) > _CACHE_MAX:
            for k in sorted(self._cache)[: _CACHE_MAX // 2]:
                self._cache.pop(k, None)
        return pred

    def predict(self, frame) -> Optional[Tuple[float, float]]:
        if not self.ok or not getattr(frame, "face_present", False):
            return None
        cached = self._cache.get(float(frame.t_sec))
        if cached is not None:
            return cached
        if is_blink(frame):
            return self._last_pred if self._last_pred is not None else (0.5, 0.5)
        lh, lv = self._look(frame)
        return self._map(frame.yaw, frame.pitch, frame.iris_x, frame.iris_y, lh, lv)

    def is_on_screen(self, frame, margin: Optional[float] = None) -> bool:
        """True when mapped gaze is inside the screen box (+margin)."""
        m = self.margin if margin is None else float(margin)
        p = self.predict(frame)
        if p is None:
            return False
        sx, sy = p
        return (-m <= sx <= 1.0 + m) and (-m <= sy <= 1.0 + m)

    def to_dict(self) -> dict:
        return {
            "ok": bool(self.ok),
            "residual": None if not np.isfinite(self.residual) else round(self.residual, 4),
            "n_dots": int(self.n_dots),
            "freeze_head": bool(self.freeze_head),
            "margin": float(self.margin),
        }

    def export_state(self) -> Optional[dict]:
        """Serialise fitted coefficients for persistence. None if not fitted."""
        if not self.ok or self._cx is None or self._cy is None:
            return None
        residual = None if not np.isfinite(self.residual) else float(self.residual)
        return {
            "ok": True,
            "cx": [float(v) for v in self._cx],
            "cy": [float(v) for v in self._cy],
            "residual": residual,
            "n_dots": int(self.n_dots),
            "freeze_head": bool(self.freeze_head),
            "margin": float(self.margin),
        }

    def load_state(self, state: Optional[dict]) -> bool:
        """Restore coefficients from ``export_state``. Returns True on success."""
        self.ok = False
        self.residual = float("inf")
        self.n_dots = 0
        self._cx = self._cy = None
        self.reset_history()
        if not state or not isinstance(state, dict) or state.get("ok") is False:
            return False
        try:
            cx = np.asarray(state["cx"], dtype=np.float64)
            cy = np.asarray(state["cy"], dtype=np.float64)
            if cx.ndim != 1 or cy.ndim != 1 or len(cx) < 2 or len(cy) < 2:
                return False
            if not (np.all(np.isfinite(cx)) and np.all(np.isfinite(cy))):
                return False
            residual = state.get("residual")
            residual_f = float(residual) if residual is not None else 0.0
            if residual is not None and (
                not np.isfinite(residual_f) or residual_f >= self.max_residual
            ):
                return False
            self._cx = cx
            self._cy = cy
            self.residual = residual_f if np.isfinite(residual_f) else 0.0
            self.n_dots = int(state.get("n_dots") or 0)
            self.freeze_head = bool(state.get("freeze_head", False))
            if state.get("margin") is not None:
                self.margin = float(state["margin"])
            self.ok = True
            return True
        except (KeyError, TypeError, ValueError):
            return False
