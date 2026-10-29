"""Per-frame MediaPipe face + pose features (CPU)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

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


def _mat_to_ypr(mat: np.ndarray) -> Tuple[float, float, float]:
    """Extract yaw/pitch/roll (degrees) from a 4x4 facial transformation matrix."""
    r = np.asarray(mat, dtype=np.float64).reshape(4, 4)[:3, :3]
    # MediaPipe facial transform: pitch from -r[2,1], yaw from r[2,0], roll from -r[1,0]
    # Use a stable ZYX-style decomposition used in many MP examples.
    sy = float(np.sqrt(r[0, 0] ** 2 + r[1, 0] ** 2))
    singular = sy < 1e-6
    if not singular:
        pitch = float(np.degrees(np.arctan2(-r[2, 0], sy)))
        yaw = float(np.degrees(np.arctan2(r[1, 0], r[0, 0])))
        roll = float(np.degrees(np.arctan2(r[2, 1], r[2, 2])))
    else:
        pitch = float(np.degrees(np.arctan2(-r[2, 0], sy)))
        yaw = float(np.degrees(np.arctan2(-r[0, 1], r[1, 1])))
        roll = 0.0
    return yaw, pitch, roll


def _iris_ratio(lms) -> Tuple[float, float]:
    """Horizontal/vertical iris position in [0,1] averaged across eyes."""

    def one(iris_i, outer_i, inner_i, top_i, bot_i):
        if max(iris_i, outer_i, inner_i, top_i, bot_i) >= len(lms):
            return 0.5, 0.5
        iris = lms[iris_i]
        outer, inner = lms[outer_i], lms[inner_i]
        top, bot = lms[top_i], lms[bot_i]
        width = abs(inner.x - outer.x) + 1e-6
        height = abs(bot.y - top.y) + 1e-6
        hx = (iris.x - min(outer.x, inner.x)) / width
        vy = (iris.y - min(top.y, bot.y)) / height
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
        self._ts_ms = max(self._ts_ms + 33, int(t_sec * 1000) + 1)

        face_res = self._face.detect_for_video(img, self._ts_ms)
        pose_res = self._pose.detect_for_video(img, self._ts_ms)

        yaw = pitch = roll = 0.0
        iris_x = iris_y = 0.5
        blink = jaw = 0.0
        face_present = bool(face_res.face_landmarks)

        if face_present:
            lms = face_res.face_landmarks[0]
            iris_x, iris_y = _iris_ratio(lms)
            blink = _blendshape_score(
                face_res.face_blendshapes, ("eyeBlinkLeft", "eyeBlinkRight")
            )
            jaw = _blendshape_score(face_res.face_blendshapes, ("jawOpen",))
            if face_res.facial_transformation_matrixes:
                yaw, pitch, roll = _mat_to_ypr(face_res.facial_transformation_matrixes[0])

        hand_to_face = 0.0
        body_motion = 0.0
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
            # Fallback head proxy if face missing but pose present
            if not face_present:
                ls, rs = pl[_POSE_L_SHOULDER], pl[_POSE_R_SHOULDER]
                mid_x = 0.5 * (ls.x + rs.x)
                mid_y = 0.5 * (ls.y + rs.y)
                sh_w = abs(rs.x - ls.x) + 1e-6
                yaw = float(np.clip((nose.x - mid_x) / sh_w * 45.0, -60, 60))
                pitch = float(np.clip((nose.y - mid_y) / sh_w * 45.0, -60, 60))
                face_present = float(nose.visibility) > 0.5

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
        )
