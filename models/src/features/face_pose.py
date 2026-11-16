"""Per-frame MediaPipe face + pose features (CPU)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

# MediaPipe logs this on every landmarker load. It is expected for these
# task models and does not affect inference.
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("ABSL_MIN_LOG_LEVEL", "2")


@contextmanager
def _silence_native_stderr():
    """Drop C++ stderr from MediaPipe while a landmarker is created."""
    try:
        saved = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
    except OSError:
        yield
        return
    try:
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(devnull)

# Face mesh indices (MediaPipe FaceLandmarker topology)
_LEFT_IRIS = 468
_RIGHT_IRIS = 473
_LEFT_EYE_OUTER, _LEFT_EYE_INNER = 33, 133
_RIGHT_EYE_OUTER, _RIGHT_EYE_INNER = 263, 362
_LEFT_EYE_TOP, _LEFT_EYE_BOT = 159, 145
_RIGHT_EYE_TOP, _RIGHT_EYE_BOT = 386, 374

_POSE_NOSE = 0
_POSE_L_SHOULDER = 11
_POSE_R_SHOULDER = 12
_POSE_L_WRIST = 15
_POSE_R_WRIST = 16


@dataclass
class FrameFeatures:
    t_sec: float
    face_present: bool
    yaw: float
    pitch: float
    roll: float
    iris_x: float
    iris_y: float
    blink: float
    jaw_open: float
    hand_to_face: float
    body_motion: float
    nose_x: float
    nose_y: float
    body_present: bool = False
    # PLAN 8: MediaPipe eye-look blendshapes (defaults keep old callers working)
    look_h: float = 0.0
    look_v: float = 0.0
    look_down: float = 0.0


def _mat_to_ypr(mat: np.ndarray) -> Tuple[float, float, float]:
    """Extract yaw/pitch/roll (degrees) from a 4x4 facial transformation matrix."""
    r = np.asarray(mat, dtype=np.float64).reshape(4, 4)[:3, :3]
    # MediaPipe face space is y-up: yaw (shake) is about y, pitch (nod) about x,
    # roll (tilt) about z. Decompose R = Rz(roll) @ Ry(yaw) @ Rx(pitch).
    # (v2 named these axes z/y/x → yaw/pitch/roll, i.e. "yaw" was actually tilt;
    # confirmed on S01 distracted.mp4: head turns moved the old "pitch".)
    cy = float(np.sqrt(r[2, 1] ** 2 + r[2, 2] ** 2))
    yaw = float(np.degrees(np.arctan2(-r[2, 0], cy)))
    if cy > 1e-6:
        pitch = float(np.degrees(np.arctan2(r[2, 1], r[2, 2])))
        roll = float(np.degrees(np.arctan2(r[1, 0], r[0, 0])))
    else:
        pitch = float(np.degrees(np.arctan2(-r[1, 2], r[1, 1])))
        roll = 0.0
    return yaw, pitch, roll


def _iris_ratio(lms) -> Tuple[float, float]:
    """Horizontal/vertical iris position in [0,1] averaged across eyes.

    PLAN 8: vertical is measured vs the **eye-corner midline** (corners don't
    move with the lids) and normalised by eye width, so looking up/down is
    visible. Horizontal is unchanged (outer→inner).
    """

    def one(iris_i, outer_i, inner_i, top_i, bot_i):
        if max(iris_i, outer_i, inner_i, top_i, bot_i) >= len(lms):
            return 0.5, 0.5
        iris = lms[iris_i]
        outer, inner = lms[outer_i], lms[inner_i]
        width = abs(inner.x - outer.x) + 1e-6
        hx = (iris.x - min(outer.x, inner.x)) / width
        # Corner midline: lids track the eyeball; corners stay put.
        mid_y = 0.5 * (outer.y + inner.y)
        vy = 0.5 + (iris.y - mid_y) / width
        return float(np.clip(hx, 0.0, 1.0)), float(np.clip(vy, 0.0, 1.0))

    lx, ly = one(_LEFT_IRIS, _LEFT_EYE_OUTER, _LEFT_EYE_INNER, _LEFT_EYE_TOP, _LEFT_EYE_BOT)
    rx, ry = one(_RIGHT_IRIS, _RIGHT_EYE_OUTER, _RIGHT_EYE_INNER, _RIGHT_EYE_TOP, _RIGHT_EYE_BOT)
    return 0.5 * (lx + rx), 0.5 * (ly + ry)


def _blendshape_score(blendshapes, names: Tuple[str, ...]) -> float:
    if not blendshapes:
        return 0.0
    cats = blendshapes[0]
    by_name = {c.category_name: float(c.score) for c in cats}
    vals = [by_name[n] for n in names if n in by_name]
    return float(np.mean(vals)) if vals else 0.0


class FrameFeatureExtractor:
    """CPU MediaPipe FaceLandmarker + PoseLandmarker (VIDEO mode)."""

    def __init__(
        self,
        face_task: Optional[Path] = None,
        pose_task: Optional[Path] = None,
    ):
        import mediapipe as mp

        root = Path(__file__).resolve().parent
        face_task = face_task or (root / "face_landmarker.task")
        pose_task = pose_task or (
            root.parent / "model4_engagement" / "pose_landmarker_lite.task"
        )
        if not face_task.exists():
            raise FileNotFoundError(f"Missing FaceLandmarker task: {face_task}")
        if not pose_task.exists():
            raise FileNotFoundError(f"Missing PoseLandmarker task: {pose_task}")

        self._mp = mp
        BaseOptions = mp.tasks.BaseOptions
        FaceLandmarker = mp.tasks.vision.FaceLandmarker
        FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
        PoseLandmarker = mp.tasks.vision.PoseLandmarker
        PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
        RunningMode = mp.tasks.vision.RunningMode

        with _silence_native_stderr():
            self._face = FaceLandmarker.create_from_options(
                FaceLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=str(face_task)),
                    running_mode=RunningMode.VIDEO,
                    output_face_blendshapes=True,
                    output_facial_transformation_matrixes=True,
                    num_faces=1,
                    min_face_detection_confidence=0.4,
                    min_face_presence_confidence=0.4,
                    min_tracking_confidence=0.4,
                )
            )
            self._pose = PoseLandmarker.create_from_options(
                PoseLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=str(pose_task)),
                    running_mode=RunningMode.VIDEO,
                    min_pose_detection_confidence=0.5,
                )
            )
        self._ts_ms = 0
        self._prev_nose: Optional[Tuple[float, float]] = None

    def close(self) -> None:
        for obj in (self._face, self._pose):
            close = getattr(obj, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    def reset(self) -> None:
        """Restart temporal state between clips (recreate landmarkers)."""
        self.close()
        # Re-init with same task paths via __init__ fields is awkward; callers
        # should construct a fresh extractor per clip. Keep method for API clarity.
        self._ts_ms = 0
        self._prev_nose = None

    def process(self, frame_bgr: np.ndarray, t_sec: float) -> FrameFeatures:
        mp = self._mp
        rgb = frame_bgr[:, :, ::-1].copy()
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        # VIDEO mode needs strictly increasing timestamps; use the real frame time.
        self._ts_ms = max(self._ts_ms + 1, int(t_sec * 1000))

        face_res = self._face.detect_for_video(img, self._ts_ms)
        pose_res = self._pose.detect_for_video(img, self._ts_ms)

        yaw = pitch = roll = 0.0
        iris_x = iris_y = 0.5
        blink = jaw = 0.0
        look_h = look_v = look_down = 0.0
        face_present = bool(face_res.face_landmarks)

        if face_present:
            lms = face_res.face_landmarks[0]
            iris_x, iris_y = _iris_ratio(lms)
            blink = _blendshape_score(
                face_res.face_blendshapes, ("eyeBlinkLeft", "eyeBlinkRight")
            )
            jaw = _blendshape_score(face_res.face_blendshapes, ("jawOpen",))
            # PLAN 8: eye-look blendshapes (signed; positive = look right / up)
            out_l = _blendshape_score(face_res.face_blendshapes, ("eyeLookOutLeft",))
            in_r = _blendshape_score(face_res.face_blendshapes, ("eyeLookInRight",))
            in_l = _blendshape_score(face_res.face_blendshapes, ("eyeLookInLeft",))
            out_r = _blendshape_score(face_res.face_blendshapes, ("eyeLookOutRight",))
            look_h = 0.5 * (out_l + in_r) - 0.5 * (in_l + out_r)
            up = _blendshape_score(
                face_res.face_blendshapes, ("eyeLookUpLeft", "eyeLookUpRight")
            )
            down = _blendshape_score(
                face_res.face_blendshapes, ("eyeLookDownLeft", "eyeLookDownRight")
            )
            look_v = up - down
            look_down = down
            if face_res.facial_transformation_matrixes:
                yaw, pitch, roll = _mat_to_ypr(face_res.facial_transformation_matrixes[0])

        hand_to_face = 0.0
        body_motion = 0.0
        body_present = False
        nose_x = nose_y = 0.5
        if pose_res.pose_landmarks:
            pl = pose_res.pose_landmarks[0]
            nose = pl[_POSE_NOSE]
            nose_x, nose_y = float(nose.x), float(nose.y)
            if self._prev_nose is not None:
                body_motion = float(
                    np.hypot(nose_x - self._prev_nose[0], nose_y - self._prev_nose[1])
                )
            self._prev_nose = (nose_x, nose_y)

            def dist(a, b):
                return float(np.hypot(a.x - b.x, a.y - b.y))

            lw, rw = pl[_POSE_L_WRIST], pl[_POSE_R_WRIST]
            hand_to_face = float(
                min(
                    dist(lw, nose) if lw.visibility > 0.3 else 1.0,
                    dist(rw, nose) if rw.visibility > 0.3 else 1.0,
                )
            )
            body_present = float(nose.visibility) > 0.5 and max(
                float(pl[_POSE_L_SHOULDER].visibility), float(pl[_POSE_R_SHOULDER].visibility)
            ) > 0.5
            # Fallback head proxy if face missing but pose present. face_present
            # stays False: it must mean the FaceLandmarker actually found a face.
            if not face_present:
                ls, rs = pl[_POSE_L_SHOULDER], pl[_POSE_R_SHOULDER]
                mid_x = 0.5 * (ls.x + rs.x)
                mid_y = 0.5 * (ls.y + rs.y)
                sh_w = abs(rs.x - ls.x) + 1e-6
                yaw = float(np.clip((nose.x - mid_x) / sh_w * 45.0, -60, 60))
                pitch = float(np.clip((nose.y - mid_y) / sh_w * 45.0, -60, 60))

        return FrameFeatures(
            t_sec=float(t_sec),
            face_present=bool(face_present),
            yaw=float(yaw),
            pitch=float(pitch),
            roll=float(roll),
            iris_x=float(iris_x),
            iris_y=float(iris_y),
            blink=float(blink),
            jaw_open=float(jaw),
            hand_to_face=float(hand_to_face),
            body_motion=float(body_motion),
            nose_x=float(nose_x),
            nose_y=float(nose_y),
            body_present=bool(body_present),
            look_h=float(look_h),
            look_v=float(look_v),
            look_down=float(look_down),
        )
