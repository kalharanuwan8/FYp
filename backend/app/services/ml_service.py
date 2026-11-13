"""
In-process ML service.

Live path (v3): each session gets a LiveWindowScorer (models/src/features/live.py)
that runs the same MediaPipe feature code as model6 training, then the v3
model6 pack (nested-LOSO) + hysteresis. Without a v3 pack the same features
feed a transparent rule (ml_mode="rule").

Legacy path: Model 1 Gaze + Model 2 Pose + Model 4 Engagement → Model 5 Fusion,
used only when those checkpoints exist (they are not in the repo).
"""
from __future__ import annotations

import base64
import os
import sys
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np

GAZE_LABELS = {0: "center", 1: "left", 2: "right", 3: "down"}

FUSION_FEATURES_DEFAULT = [
    "p_center_mean", "p_left_mean", "p_right_mean", "p_down_mean",
    "gaze_away_ratio",
    "yaw_mean", "pitch_mean", "roll_mean",
    "yaw_std", "pitch_std", "roll_std",
    "engagement_prob_mean",
]

# model6 temporal decision (seconds). Short glances stay FOCUSED.
HYST_ENTER_PROB = 0.6
HYST_EXIT_PROB = 0.4
HYST_ENTER_SEC = 3.0
HYST_EXIT_SEC = 2.0

# Rule fallback (no v3 pack): distraction_proxy/2 >= 0.275 is the proxy >= 0.55
# cut-off of the original label rule (models/src/features/windows.py).
RULE_PROXY_THRESHOLD = 0.275
# A window counts as "no face" below this face_present_ratio.
NO_FACE_RATIO = 0.2
BODY_PRESENT_RATIO = 0.5

MODEL6_FEATURE_NAMES = [
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
# PLAN 4: face_present_ratio below this → UNKNOWN low_face (don't score as off-screen).
LOW_FACE_RATIO = 0.6

_LM_IDX = {
    "nose": 0, "l_shoulder": 11, "r_shoulder": 12,
    "l_elbow": 13, "r_elbow": 14, "l_wrist": 15, "r_wrist": 16,
}


class MLService:
    """
    Singleton wrapper around gaze / pose / engagement / fusion checkpoints.
    Accumulates per-session frame windows so fusion sees aggregates, not single frames.
    """
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super(MLService, cls).__new__(cls)
                    instance._init_models()
                    cls._instance = instance
        return cls._instance

    @staticmethod
    def _load_checkpoint(torch, path, map_location):
        """Prefer weights_only; fall back for local project checkpoints with metadata."""
        try:
            return torch.load(path, map_location=map_location, weights_only=True)
        except Exception:
            return torch.load(path, map_location=map_location, weights_only=False)

    def _init_models(self):
        self.models_dir = Path(__file__).resolve().parent.parent.parent.parent / "models"
        # Repo root must be on sys.path so joblib can unpickle
        # models.src.model6_natural.wrapper.Model6SklearnWrapper.
        repo_root = self.models_dir.parent
        for p in (str(repo_root), str(self.models_dir)):
            if p not in sys.path:
                sys.path.insert(0, p)

        self.device = "cpu"
        self.ml_mode = "fallback"  # "full" | "partial" | "fallback"
        self.gaze_model = None
        self.gaze_tf = None
        self.pose_model = None
        self.pose_tf = None
        self.eng_model = None
        self.eng_feature_cols: List[str] = []
        self.fusion_model = None
        self.fusion_threshold = 0.5
        self.fusion_feat_names = list(FUSION_FEATURES_DEFAULT)
        self.fusion_kind = "model5"  # "model5" | "model6_mlp"
        self.fusion_version = ""  # "v3_nested_loso" for packs usable on the live path
        self.fusion_hysteresis: Optional[dict] = None
        # v3 live path: one LiveWindowScorer + lock per session
        self._live_available = False
        self._live_scorers: Dict[Any, Any] = {}
        self._session_locks: Dict[Any, threading.RLock] = {}
        self._session_last_seen: Dict[Any, float] = {}
        self._session_t0: Dict[Any, float] = {}
        self._state_lock = threading.RLock()
        self.live_window_sec = float(os.environ.get("ML_LIVE_WINDOW_SEC", "5.0"))
        # ~15 face frames ≈ 7.5 s at 2 fps — fits the 10 s calibration screen.
        self.live_baseline_frames = int(os.environ.get("ML_LIVE_BASELINE_FRAMES", "15"))
        self.session_idle_sec = float(os.environ.get("ML_SESSION_IDLE_SEC", "600"))
        # Per-session hysteresis for fusion probabilities
        self._session_hyst_state: Dict[Any, str] = {}
        self._session_hyst_high_t0: Dict[Any, Optional[float]] = {}
        self._session_hyst_low_t0: Dict[Any, Optional[float]] = {}
        self._session_hyst_last_t: Dict[Any, Optional[float]] = {}
        self._session_no_body_t0: Dict[Any, Optional[float]] = {}
        # Shared task path only — each session gets its own VIDEO landmarker
        # so temporal tracking state never crosses sessions (Phase 2A).
        self._pose_landmarker_task_path: Optional[Path] = None
        self._session_landmarkers: Dict[Any, Any] = {}
        self._session_lm_ts: Dict[Any, int] = {}  # strictly increasing ms per session
        self._mp_available = False
        self._mp_module = None
        self._torch = None
        self._Image = None

        try:
            self.face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            self.eye_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_eye.xml"
            )
        except Exception as err:
            print(f"[MLService] Warning: Haar cascades unavailable ({err})")
            self.face_cascade = None
            self.eye_cascade = None

        # Face gate (engineering params). Defaults from evaluation/thesis_numbers
        # raw/face_gate_check.json chosen settings (ms28_n5); override via env.
        self.face_upscale = float(os.environ.get("ML_FACE_UPSCALE", "1.0"))
        self.face_min_neighbors = int(os.environ.get("ML_FACE_MIN_NEIGHBORS", "5"))
        self.face_min_size = int(os.environ.get("ML_FACE_MIN_SIZE", "28"))
        self.face_equalize = (
            os.environ.get("ML_FACE_EQUALIZE", "false").lower() == "true"
        )

        # Live heartbeats are ~0.5 Hz; keep enough frames for M4 movement features
        # (needs ≥2 valid landmarks). Default 5 ≈ 10 s window window.
        self.window_size = int(os.environ.get("ML_WINDOW_FRAMES", "5"))
        # Session pose baseline: median yaw/pitch of first K face-present frames
        # (laptop geometry vs BIWI); subtracted before fusion. No retrain.
        self.pose_baseline_frames = int(os.environ.get("ML_POSE_BASELINE_FRAMES", "8"))
        self._session_bufs: Dict[Any, Dict[str, Deque]] = defaultdict(self._new_session_buf)
        self._session_pose_samples: Dict[Any, List[List[float]]] = defaultdict(list)
        self._session_pose_baseline: Dict[Any, Optional[Tuple[float, float]]] = {}
        self._session_hyst_state = {}
        self._session_hyst_high_t0 = {}
        self._session_hyst_low_t0 = {}
        self._session_hyst_last_t = {}
        self._session_no_body_t0 = {}

        self._load_torch_models()
        self._load_sklearn_models()
        # Env override of the trained threshold is an explicit experiment switch,
        # never a silent deployment setting.
        env_thr = os.environ.get("ML_FUSION_THRESHOLD", "").strip()
        if env_thr and os.environ.get("ML_ALLOW_THRESHOLD_OVERRIDE") != "1":
            print(
                "[MLService] Ignoring ML_FUSION_THRESHOLD (set "
                "ML_ALLOW_THRESHOLD_OVERRIDE=1 to override the trained threshold)"
            )
            env_thr = ""
        if env_thr:
            try:
                self.fusion_threshold = float(env_thr)
                print(f"[MLService] ML_FUSION_THRESHOLD override={self.fusion_threshold}")
            except ValueError:
                print(f"[MLService] Warning: invalid ML_FUSION_THRESHOLD={env_thr!r}")
        self._init_mediapipe()
        self._update_ml_mode()
        print(
            f"[MLService] Ready (ml_mode={self.ml_mode}, "
            f"fusion_threshold={self.fusion_threshold}, "
            f"models_dir={self.models_dir})"
        )

    @staticmethod
    def _new_session_buf() -> Dict[str, Deque]:
        return {
            "gaze": deque(maxlen=32),
            "pose": deque(maxlen=32),
            "lm": deque(maxlen=32),
        }

    def _ckpt(self, *parts: str) -> Path:
        return self.models_dir.joinpath(*parts)

    def _load_torch_models(self):
        gaze_ckpt = Path(os.environ.get(
            "GAZE_CKPT",
            str(self._ckpt("outputs", "checkpoints", "model1_gaze", "best.pt")),
        ))
        pose_ckpt = Path(os.environ.get(
            "POSE_CKPT",
            str(self._ckpt("outputs", "checkpoints", "model2_pose", "best.pt")),
        ))

        try:
            import torch
            import torch.nn as nn
            from PIL import Image
            from torchvision import transforms as T, models
            from torchvision.models import mobilenet_v2

            self._torch = torch
            self._Image = Image
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

            if gaze_ckpt.exists():
                ckpt = self._load_checkpoint(torch, gaze_ckpt, self.device)
                m = mobilenet_v2(weights=None)
                m.classifier[1] = nn.Linear(m.classifier[1].in_features, ckpt["num_classes"])
                m.load_state_dict(ckpt["model_state"])
                m.to(self.device).eval()
                img_size = ckpt.get("img_size", 224)
                self.gaze_model = m
                self.gaze_tf = T.Compose([
                    T.Resize((img_size, img_size)),
                    T.ToTensor(),
                    T.Lambda(lambda x: x.repeat(3, 1, 1) if x.shape[0] == 1 else x),
                    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
                ])
                print(f"[MLService] Loaded gaze model from {gaze_ckpt.name}")
            else:
                print(f"[MLService] Warning: gaze checkpoint missing: {gaze_ckpt}")

            if pose_ckpt.exists():
                ckpt = self._load_checkpoint(torch, pose_ckpt, self.device)
                m = models.resnet18(weights=None)
                m.fc = nn.Linear(m.fc.in_features, 3)
                state = {k.replace("net.", ""): v for k, v in ckpt["model"].items()}
                m.load_state_dict(state)
                m.to(self.device).eval()
                self.pose_model = m
                self.pose_tf = T.Compose([
                    T.Resize((224, 224)),
                    T.ToTensor(),
                    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
                ])
                print(f"[MLService] Loaded pose model from {pose_ckpt.name}")
            else:
                print(f"[MLService] Warning: pose checkpoint missing: {pose_ckpt}")

        except Exception as e:
            print(f"[MLService] Warning: torch models unavailable ({e})")

    def _load_sklearn_models(self):
        import joblib

        eng_ckpt = Path(os.environ.get(
            "ENG_CKPT",
            str(self._ckpt("outputs", "checkpoints", "model4_engagement", "model.pkl")),
        ))
        # Prefer newest model6 pack (v4 → v3 → natural); else model5.
        env_fusion = os.environ.get("FUSION_CKPT", "").strip()
        model6_v4_ckpt = self._ckpt("outputs", "checkpoints", "model6_v4", "model.pkl")
        model6_v3_ckpt = self._ckpt("outputs", "checkpoints", "model6_v3", "model.pkl")
        model6_ckpt = self._ckpt("outputs", "checkpoints", "model6_natural", "model.pkl")
        model5_ckpt = self._ckpt("outputs", "checkpoints", "model5_fusion", "model.pkl")
        if env_fusion:
            fusion_ckpt = Path(env_fusion)
        elif model6_v4_ckpt.exists():
            fusion_ckpt = model6_v4_ckpt
        elif model6_v3_ckpt.exists():
            fusion_ckpt = model6_v3_ckpt
        elif model6_ckpt.exists():
            fusion_ckpt = model6_ckpt
        else:
            fusion_ckpt = model5_ckpt

        if eng_ckpt.exists():
            try:
                pack = joblib.load(eng_ckpt)
                self.eng_model = pack["model"] if isinstance(pack, dict) else pack
                self.eng_feature_cols = pack.get("feature_cols", []) if isinstance(pack, dict) else []
                print(f"[MLService] Loaded engagement model from {eng_ckpt.name}")
            except Exception as e:
                print(f"[MLService] Warning: could not load engagement model: {e}")
        else:
            print(f"[MLService] Warning: engagement checkpoint missing: {eng_ckpt}")

        if fusion_ckpt.exists():
            try:
                pack = joblib.load(fusion_ckpt)
                if isinstance(pack, dict) and "model" in pack:
                    self.fusion_model = pack["model"]
                    self.fusion_threshold = float(pack.get("threshold", 0.5))
                    self.fusion_feat_names = list(
                        pack.get("features", FUSION_FEATURES_DEFAULT)
                    )
                    self.fusion_kind = str(pack.get("kind", "model5"))
                    self.fusion_version = str(pack.get("version", ""))
                    self.fusion_hysteresis = pack.get("hysteresis")
                else:
                    self.fusion_model = pack
                    self.fusion_kind = "model5"
                print(
                    f"[MLService] Loaded fusion model from {fusion_ckpt} "
                    f"(kind={self.fusion_kind}, version={self.fusion_version or 'legacy'})"
                )
            except Exception as e:
                print(f"[MLService] Warning: could not load fusion model: {e}")
        else:
            print(f"[MLService] Warning: fusion checkpoint missing: {fusion_ckpt}")

    def _init_mediapipe(self):
        """Resolve task asset; landmarker instances are created per session."""
        task_path = self._ckpt("src", "model4_engagement", "pose_landmarker_lite.task")
        try:
            import mediapipe as mp
            if not task_path.exists():
                print(f"[MLService] Warning: MediaPipe task missing: {task_path}")
                return
            self._mp_module = mp
            self._pose_landmarker_task_path = task_path
            self._mp_available = True
            face_task = self._ckpt("src", "features", "face_landmarker.task")
            self._live_available = face_task.exists()
            if not self._live_available:
                print(f"[MLService] Warning: FaceLandmarker task missing: {face_task}")
            print(
                "[MLService] MediaPipe PoseLandmarker ready "
                "(per-session VIDEO instances; no shared tracker)"
            )
        except Exception as e:
            print(f"[MLService] Warning: MediaPipe unavailable ({e})")

    def _create_session_landmarker(self):
        """Fresh VIDEO-mode PoseLandmarker with isolated temporal state."""
        mp = self._mp_module
        if mp is None or self._pose_landmarker_task_path is None:
            return None
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(self._pose_landmarker_task_path)
            ),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            min_pose_detection_confidence=0.5,
        )
        return mp.tasks.vision.PoseLandmarker.create_from_options(options)

    def _landmarker_for_session(self, session_id: Any):
        if not self._mp_available:
            return None
        if session_id not in self._session_landmarkers:
            try:
                lm = self._create_session_landmarker()
            except Exception as e:
                print(f"[MLService] Failed to create session landmarker: {e}")
                return None
            if lm is None:
                return None
            self._session_landmarkers[session_id] = lm
            self._session_lm_ts[session_id] = 0
        return self._session_landmarkers[session_id]

    def _next_landmark_timestamp_ms(self, session_id: Any) -> int:
        """Strictly increasing timestamp for this session's landmarker only."""
        prev = self._session_lm_ts.get(session_id, 0)
        # Advance by at least 1 ms; prefer wall-delta from last call when available.
        nxt = prev + max(1, int(round(1000.0 / max(self.window_size, 1))))
        # Also allow real elapsed spacing without colliding with other sessions
        # (each session has its own counter starting at 0).
        wall_step = prev + 33  # ~30 fps-equivalent step as a floor when heartbeats are slow
        nxt = max(nxt, wall_step)
        self._session_lm_ts[session_id] = nxt
        return nxt

    def _close_session_landmarker(self, session_id: Any) -> None:
        landmarker = self._session_landmarkers.pop(session_id, None)
        self._session_lm_ts.pop(session_id, None)
        if landmarker is None:
            return
        close = getattr(landmarker, "close", None)
        if callable(close):
            try:
                close()
            except Exception as e:
                print(f"[MLService] Landmarker close warning for session {session_id}: {e}")

    def _uses_live_path(self) -> bool:
        """Shared-feature path unless the full legacy M1/M2 pipeline is present."""
        legacy_complete = self.gaze_model is not None and self.pose_model is not None
        return self._live_available and not legacy_complete

    def _has_v3_pack(self) -> bool:
        """True when a nested-LOSO model6 pack (MLP or logreg, v3+) is loaded."""
        if self.fusion_model is None:
            return False
        if self.fusion_kind not in ("model6_mlp", "model6_logreg"):
            return False
        ver = self.fusion_version or ""
        return ver.startswith("v3") or ver.startswith("v4")

    def _update_ml_mode(self):
        if self._uses_live_path():
            if self._has_v3_pack():
                self.ml_mode = "model6"
            else:
                self.ml_mode = "rule"
                print(
                    "[MLService] WARNING: live path active but no model6 v3/v4 pack — "
                    "ml_mode=rule (distraction_proxy). Deploy models/outputs/checkpoints/"
                    "model6_v4/model.pkl to restore model scoring."
                )
            return
        has_gaze = self.gaze_model is not None
        has_pose = self.pose_model is not None
        has_eng = self.eng_model is not None
        has_fusion = self.fusion_model is not None
        if has_gaze and has_pose and has_eng and has_fusion:
            self.ml_mode = "full"
        elif has_gaze or has_pose or has_eng or has_fusion:
            self.ml_mode = "partial"
        else:
            self.ml_mode = "fallback"

    def clear_session(self, session_id: Any):
        """Drop frame buffers and destroy this session's MediaPipe landmarker."""
        self._session_bufs.pop(session_id, None)
        self._session_pose_samples.pop(session_id, None)
        self._session_pose_baseline.pop(session_id, None)
        self._session_hyst_state.pop(session_id, None)
        self._session_hyst_high_t0.pop(session_id, None)
        self._session_hyst_low_t0.pop(session_id, None)
        self._session_hyst_last_t.pop(session_id, None)
        self._session_no_body_t0.pop(session_id, None)
        self._close_session_landmarker(session_id)
        with self._state_lock:
            scorer = self._live_scorers.pop(session_id, None)
            self._session_locks.pop(session_id, None)
            self._session_last_seen.pop(session_id, None)
            self._session_t0.pop(session_id, None)
        if scorer is not None:
            try:
                scorer.close()
            except Exception as e:
                print(f"[MLService] Scorer close warning for session {session_id}: {e}")

    def shutdown(self) -> None:
        """Release all per-session MediaPipe resources (needed for clean pytest exit)."""
        session_ids = set(self._session_landmarkers) | set(self._live_scorers) | set(self._session_bufs)
        for sid in list(session_ids):
            try:
                self.clear_session(sid)
            except Exception as e:
                print(f"[MLService] shutdown warning for session {sid}: {e}")
        self._session_landmarkers.clear()
        self._live_scorers.clear()

    def _apply_hysteresis(
        self,
        session_id: Any,
        dist_prob: float,
        now: Optional[float] = None,
        params: Optional[dict] = None,
    ) -> str:
        """Enter DISTRACTED only after sustained high prob; exit after sustained low.

        Same state machine as models/src/model6_natural/train.replay_hysteresis.
        ``now`` is the frame timestamp on the live path (wall clock otherwise);
        ``params`` come from the v3 pack.
        """
        p = params or {}
        enter_prob = float(p.get("enter_prob", HYST_ENTER_PROB))
        enter_sec = float(p.get("enter_sec", HYST_ENTER_SEC))
        exit_prob = float(p.get("exit_prob", HYST_EXIT_PROB))
        exit_sec = float(p.get("exit_sec", HYST_EXIT_SEC))
        now = time.monotonic() if now is None else float(now)
        # Reset timers when the gap since the last scored window is too large
        # (2× typical 2 s heartbeat) so stale high_t0 cannot fire later.
        last = self._session_hyst_last_t.get(session_id)
        if last is not None and (now - float(last)) > 4.0:
            self._session_hyst_high_t0[session_id] = None
            self._session_hyst_low_t0[session_id] = None
        self._session_hyst_last_t[session_id] = now
        state = self._session_hyst_state.get(session_id, "FOCUSED")
        if dist_prob >= enter_prob:
            if self._session_hyst_high_t0.get(session_id) is None:
                self._session_hyst_high_t0[session_id] = now
            self._session_hyst_low_t0[session_id] = None
            held = now - float(self._session_hyst_high_t0[session_id])
            if held >= enter_sec:
                state = "DISTRACTED"
        elif dist_prob < exit_prob:
            if self._session_hyst_low_t0.get(session_id) is None:
                self._session_hyst_low_t0[session_id] = now
            self._session_hyst_high_t0[session_id] = None
            held = now - float(self._session_hyst_low_t0[session_id])
            if held >= exit_sec:
                state = "FOCUSED"
        else:
            # Mid band: freeze timers so brief dips do not reset enter/exit
            pass
        self._session_hyst_state[session_id] = state
        return state

    @staticmethod
    def _landmarks_indicate_person(lm: Optional[dict]) -> bool:
        """True when MediaPipe returns a usable torso (nose + a shoulder)."""
        if not lm:
            return False
        nose_vis = float(lm.get("nose_vis") or 0.0)
        ls_vis = float(lm.get("l_shoulder_vis") or 0.0)
        rs_vis = float(lm.get("r_shoulder_vis") or 0.0)
        if nose_vis != nose_vis or ls_vis != ls_vis or rs_vis != rs_vis:
            return False  # NaN
        return nose_vis > 0.5 and (ls_vis > 0.5 or rs_vis > 0.5)

    def _update_pose_baseline(self, session_id: Any, pose_xyz: List[float]) -> None:
        """Collect first K face-present poses; lock median yaw/pitch as baseline."""
        if session_id in self._session_pose_baseline and self._session_pose_baseline[session_id] is not None:
            return
        samples = self._session_pose_samples[session_id]
        if len(samples) < self.pose_baseline_frames:
            samples.append([float(pose_xyz[0]), float(pose_xyz[1]), float(pose_xyz[2])])
        if len(samples) >= self.pose_baseline_frames:
            yaw_med = float(np.median([s[0] for s in samples]))
            pitch_med = float(np.median([s[1] for s in samples]))
            self._session_pose_baseline[session_id] = (yaw_med, pitch_med)

    def _centered_pose_buf(
        self, session_id: Any, pose_buf: List
    ) -> Tuple[List, Optional[float], Optional[float]]:
        """Subtract session yaw/pitch baseline from pose samples for fusion."""
        baseline = self._session_pose_baseline.get(session_id)
        if baseline is None:
            return list(pose_buf), None, None
        yaw0, pitch0 = baseline
        centered = [
            [float(p[0]) - yaw0, float(p[1]) - pitch0, float(p[2])]
            for p in pose_buf
        ]
        return centered, yaw0, pitch0

    # ── Detection helpers (from models/webcam_test.py) ────────────────────────

    def _detect_face(
        self, frame_bgr: np.ndarray
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Largest frontal face box in original frame coordinates, or None.

        Optionally equalises / upscales for Haar detectMultiScale, then maps
        the box back so crops stay on the original 224×224 frame (model input
        scale unchanged). Defaults come from face_gate_check.json (ms28_n5).
        """
        if self.face_cascade is None or frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
            return None
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if self.face_equalize:
            gray = cv2.equalizeHist(gray)
        scale = float(self.face_upscale) if self.face_upscale and self.face_upscale > 0 else 1.0
        if abs(scale - 1.0) > 1e-6:
            gray_det = cv2.resize(
                gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR
            )
        else:
            gray_det = gray
        faces = self.face_cascade.detectMultiScale(
            gray_det,
            scaleFactor=1.1,
            minNeighbors=int(self.face_min_neighbors),
            minSize=(int(self.face_min_size), int(self.face_min_size)),
        )
        if len(faces) == 0:
            return None
        fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
        if abs(scale - 1.0) > 1e-6:
            fx = int(round(fx / scale))
            fy = int(round(fy / scale))
            fw = int(round(fw / scale))
            fh = int(round(fh / scale))
        h, w = frame_bgr.shape[:2]
        fx = max(0, min(fx, w - 1))
        fy = max(0, min(fy, h - 1))
        fw = max(1, min(fw, w - fx))
        fh = max(1, min(fh, h - fy))
        return (int(fx), int(fy), int(fw), int(fh))

    def detect_eye_crop(self, frame_bgr: np.ndarray):
        if self.face_cascade is None or self.eye_cascade is None:
            return None, None
        box = self._detect_face(frame_bgr)
        if box is None:
            return None, None
        fx, fy, fw, fh = box
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        face_gray = gray[fy:fy + fh, fx:fx + fw]
        eyes = self.eye_cascade.detectMultiScale(face_gray, 1.1, 5, minSize=(12, 12))
        if len(eyes) == 0:
            return face_gray[: max(fh // 2, 1), :], (fx, fy, fw, fh // 2)
        ex, ey, ew, eh = max(eyes, key=lambda r: r[2] * r[3])
        return face_gray[ey:ey + eh, ex:ex + ew], (fx + ex, fy + ey, ew, eh)

    def detect_face_crop(self, frame_bgr: np.ndarray) -> Tuple[np.ndarray, bool]:
        h, w = frame_bgr.shape[:2]
        cw, ch = int(w * 0.6), int(h * 0.6)
        x1 = (w - cw) // 2
        y1 = (h - ch) // 2
        center = frame_bgr[y1:y1 + ch, x1:x1 + cw]
        box = self._detect_face(frame_bgr)
        if box is not None:
            fx, fy, fw, fh = box
            pad = int(fw * 0.15)
            x1 = max(0, fx - pad)
            y1 = max(0, fy - pad)
            x2 = min(frame_bgr.shape[1], fx + fw + pad)
            y2 = min(frame_bgr.shape[0], fy + fh + pad)
            return frame_bgr[y1:y2, x1:x2], True
        return center, False

    def extract_landmarks(
        self,
        frame_rgb: np.ndarray,
        session_id: Any,
    ) -> Optional[dict]:
        """
        Run pose landmarks on a per-session VIDEO landmarker.
        Temporal tracking state is isolated; timestamps never cross sessions.
        """
        landmarker = self._landmarker_for_session(session_id)
        if landmarker is None or self._mp_module is None:
            return None
        try:
            mp = self._mp_module
            timestamp_ms = self._next_landmark_timestamp_ms(session_id)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            result = landmarker.detect_for_video(mp_img, timestamp_ms)
            if not result.pose_landmarks:
                return None
            lms = result.pose_landmarks[0]
            out = {}
            for name, idx in _LM_IDX.items():
                if idx < len(lms):
                    out[f"{name}_x"] = lms[idx].x
                    out[f"{name}_y"] = lms[idx].y
                    out[f"{name}_vis"] = getattr(lms[idx], "visibility", 1.0)
                else:
                    out[f"{name}_x"] = float("nan")
                    out[f"{name}_y"] = float("nan")
                    out[f"{name}_vis"] = float("nan")
            return out
        except Exception:
            return None

    @staticmethod
    def _safe_nanmean(arr):
        return float(np.nanmean(arr)) if len(arr) > 0 else 0.0

    @staticmethod
    def _safe_nanstd(arr):
        return float(np.nanstd(arr)) if len(arr) > 0 else 0.0

    def compute_engagement_features(self, lm_buf: List[Optional[dict]]) -> dict:
        valid = [lm for lm in lm_buf if lm is not None]
        n = len(valid)
        pose_ratio = n / max(len(lm_buf), 1)

        def col(name, axis):
            return np.array([lm[f"{name}_{axis}"] for lm in valid], dtype=float)

        # Need ≥2 valid landmark frames so wrist-speed (np.diff) is defined.
        # Older live default of ML_WINDOW_FRAMES=3 never reached the previous
        # n < 4 gate, so M4 always saw the constant default vector below.
        if n < 2:
            return {
                "pose_ratio": pose_ratio,
                "lw_speed_mean": 0.0, "lw_speed_std": 0.0,
                "rw_speed_mean": 0.0, "rw_speed_std": 0.0,
                "lw_to_nose_mean": 0.5, "rw_to_nose_mean": 0.5,
                "lw_to_sh_mean": 0.3, "rw_to_sh_mean": 0.3,
                "nose_jitter": 0.0,
                "lw_below_sh_ratio": 0.5, "rw_below_sh_ratio": 0.5,
            }

        nose_xy = np.stack([col("nose", "x"), col("nose", "y")], axis=1)
        lw_xy = np.stack([col("l_wrist", "x"), col("l_wrist", "y")], axis=1)
        rw_xy = np.stack([col("r_wrist", "x"), col("r_wrist", "y")], axis=1)
        ls_xy = np.stack([col("l_shoulder", "x"), col("l_shoulder", "y")], axis=1)
        rs_xy = np.stack([col("r_shoulder", "x"), col("r_shoulder", "y")], axis=1)
        sh_mid = np.nanmean(np.stack([ls_xy, rs_xy], axis=0), axis=0)

        def speed(xy):
            d = np.diff(xy, axis=0)
            return np.sqrt(d[:, 0] ** 2 + d[:, 1] ** 2)

        lw_sp = speed(lw_xy)
        rw_sp = speed(rw_xy)
        lw_nose = np.sqrt(np.nansum((lw_xy - nose_xy) ** 2, axis=1))
        rw_nose = np.sqrt(np.nansum((rw_xy - nose_xy) ** 2, axis=1))
        lw_sh = np.sqrt(np.nansum((lw_xy - sh_mid) ** 2, axis=1))
        rw_sh = np.sqrt(np.nansum((rw_xy - sh_mid) ** 2, axis=1))
        nose_jitter = float(np.nanmean(np.nanstd(nose_xy, axis=0)))
        sh_y = sh_mid[:, 1]
        return {
            "pose_ratio": pose_ratio,
            "lw_speed_mean": self._safe_nanmean(lw_sp),
            "lw_speed_std": self._safe_nanstd(lw_sp),
            "rw_speed_mean": self._safe_nanmean(rw_sp),
            "rw_speed_std": self._safe_nanstd(rw_sp),
            "lw_to_nose_mean": self._safe_nanmean(lw_nose),
            "rw_to_nose_mean": self._safe_nanmean(rw_nose),
            "lw_to_sh_mean": self._safe_nanmean(lw_sh),
            "rw_to_sh_mean": self._safe_nanmean(rw_sh),
            "nose_jitter": nose_jitter,
            "lw_below_sh_ratio": float(np.nanmean(lw_xy[:, 1] > sh_y)),
            "rw_below_sh_ratio": float(np.nanmean(rw_xy[:, 1] > sh_y)),
        }

    def build_fusion_features(
        self,
        gaze_buf: List,
        pose_buf: List,
        eng_prob: float,
        lm_buf: Optional[List] = None,
        face_detected: bool = True,
    ) -> np.ndarray:
        gaze_arr = np.array(gaze_buf, dtype=np.float32)
        pose_arr = np.array(pose_buf, dtype=np.float32)
        p_c = float(np.mean(gaze_arr[:, 0]))
        p_l = float(np.mean(gaze_arr[:, 1]))
        p_r = float(np.mean(gaze_arr[:, 2]))
        p_d = float(np.mean(gaze_arr[:, 3]))
        gaze_away = (p_l + p_r + p_d) / max(p_c + p_l + p_r + p_d, 1e-8)
        yaw_mean = float(np.mean(pose_arr[:, 0]))
        pitch_mean = float(np.mean(pose_arr[:, 1]))
        roll_mean = float(np.mean(pose_arr[:, 2]))
        all_vals = {
            "p_center_mean": p_c,
            "p_left_mean": p_l,
            "p_right_mean": p_r,
            "p_down_mean": p_d,
            "gaze_away_ratio": gaze_away,
            "yaw_mean": yaw_mean,
            "pitch_mean": pitch_mean,
            "roll_mean": roll_mean,
            "yaw_std": float(np.std(pose_arr[:, 0])),
            "pitch_std": float(np.std(pose_arr[:, 1])),
            "roll_std": float(np.std(pose_arr[:, 2])),
            "engagement_prob_mean": eng_prob,
        }

        # model6 features are never approximated from M1/M2 outputs: they come
        # only from the shared MediaPipe extractor (predict_frames).
        if any(name in self.fusion_feat_names for name in MODEL6_FEATURE_NAMES):
            raise ValueError("model6 packs need LiveWindowScorer features (predict_frames)")

        return np.array(
            [all_vals.get(f, 0.0) for f in self.fusion_feat_names],
            dtype=np.float32,
        ).reshape(1, -1)

    def _decode_frame(self, image_base64: str) -> Optional[np.ndarray]:
        if not image_base64:
            return None
        try:
            if "," in image_base64:
                image_base64 = image_base64.split(",", 1)[1]
            img_bytes = base64.b64decode(image_base64)
            np_arr = np.frombuffer(img_bytes, np.uint8)
            return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        except Exception:
            return None

    def _infer_frame_signals(
        self,
        frame_bgr: np.ndarray,
        session_id: Any,
        face_box: Optional[Tuple[int, int, int, int]] = None,
    ):
        """Run per-frame M1/M2/landmarks. Returns (gaze_probs, pose_xyz, lm, meta)."""
        torch = self._torch
        Image = self._Image

        # Caller may pass a box from the outer face gate to avoid a second Haar.
        if face_box is None:
            face_box = self._detect_face(frame_bgr)
        face_detected = face_box is not None

        eye_crop = None
        eye_box = None
        if face_box is not None and self.eye_cascade is not None:
            fx, fy, fw, fh = face_box
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            face_gray = gray[fy:fy + fh, fx:fx + fw]
            eyes = self.eye_cascade.detectMultiScale(
                face_gray, 1.1, 5, minSize=(12, 12)
            )
            if len(eyes) == 0:
                eye_crop = face_gray[: max(fh // 2, 1), :]
                eye_box = (fx, fy, fw, fh // 2)
            else:
                ex, ey, ew, eh = max(eyes, key=lambda r: r[2] * r[3])
                eye_crop = face_gray[ey:ey + eh, ex:ex + ew]
                eye_box = (fx + ex, fy + ey, ew, eh)

        if face_box is not None:
            fx, fy, fw, fh = face_box
            pad = int(fw * 0.15)
            x1 = max(0, fx - pad)
            y1 = max(0, fy - pad)
            x2 = min(frame_bgr.shape[1], fx + fw + pad)
            y2 = min(frame_bgr.shape[0], fy + fh + pad)
            face_crop = frame_bgr[y1:y2, x1:x2]
        else:
            h, w = frame_bgr.shape[:2]
            cw, ch = int(w * 0.6), int(h * 0.6)
            x1 = (w - cw) // 2
            y1 = (h - ch) // 2
            face_crop = frame_bgr[y1:y1 + ch, x1:x1 + cw]

        gaze_probs = np.array([0.7, 0.1, 0.1, 0.1], dtype=np.float32)
        gaze_label = "center"
        gaze_conf = 0.7

        if self.gaze_model is not None and torch is not None and Image is not None:
            if eye_crop is not None:
                img_gray = Image.fromarray(eye_crop).convert("L")
            else:
                img_gray = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)).convert("L")
            with torch.no_grad():
                x = self.gaze_tf(img_gray).unsqueeze(0).to(self.device)
                logits = self.gaze_model(x).squeeze(0).cpu().numpy()
            exp = np.exp(logits - np.max(logits))
            gaze_probs = (exp / exp.sum()).astype(np.float32)
            gaze_idx = int(gaze_probs.argmax())
            gaze_label = GAZE_LABELS.get(gaze_idx, "center")
            gaze_conf = float(gaze_probs[gaze_idx])
        elif face_box is not None and self.eye_cascade is not None:
            fx, fy, fw, fh = face_box
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            face_gray = gray[fy:fy + fh, fx:fx + fw]
            eyes = self.eye_cascade.detectMultiScale(
                face_gray, 1.1, 3, minSize=(12, 12)
            )
            h, w = frame_bgr.shape[:2]
            yaw_off = abs((fx + fw / 2) - (w / 2)) / (w / 2) * 45.0
            if len(eyes) == 0 or yaw_off > 20:
                gaze_probs = np.array([0.2, 0.4, 0.3, 0.1], dtype=np.float32)
                gaze_label = "away"
                gaze_conf = 0.35
            else:
                gaze_probs = np.array([0.85, 0.05, 0.05, 0.05], dtype=np.float32)
                gaze_label = "center"
                gaze_conf = 0.92

        yaw = pitch = roll = 0.0
        if self.pose_model is not None and torch is not None and Image is not None:
            roi_rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
            pil_rgb = Image.fromarray(roi_rgb).convert("RGB")
            with torch.no_grad():
                x = self.pose_tf(pil_rgb).unsqueeze(0).to(self.device)
                raw = self.pose_model(x).squeeze(0).cpu().numpy()
            yaw, pitch, roll = float(raw[0]), float(raw[1]), float(raw[2])
        elif face_box is not None:
            h, w = frame_bgr.shape[:2]
            fx, fy, fw, fh = face_box
            yaw = abs((fx + fw / 2) - (w / 2)) / (w / 2) * 45.0

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        lm = self.extract_landmarks(frame_rgb, session_id)

        meta = {
            "face_detected": bool(face_detected),
            # Plain Python ints — numpy.int32 is not JSON-serializable.
            "face_box_px": (
                [int(v) for v in face_box] if face_box is not None else None
            ),
            "gaze_label": gaze_label,
            "gaze_confidence": gaze_conf,
            "head_pose_yaw": round(yaw, 2),
            "head_pose_pitch": round(pitch, 2),
            "head_pose_roll": round(roll, 2),
        }
        return gaze_probs, [yaw, pitch, roll], lm, meta

    def _score_window(
        self,
        gaze_buf: List,
        pose_buf: List,
        lm_buf: List,
        last_meta: dict,
        session_id: Any = None,
    ) -> Tuple[str, float, dict]:
        eng_prob = 0.5
        if self.eng_model is not None and self.eng_feature_cols:
            eng_feats = self.compute_engagement_features(lm_buf)
            eng_X = np.array(
                [[eng_feats.get(c, 0.0) for c in self.eng_feature_cols]],
                dtype=np.float32,
            )
            try:
                eng_prob = float(self.eng_model.predict_proba(eng_X)[0, 1])
            except Exception:
                eng_prob = 0.5

        features = {
            **last_meta,
            "engagement_score": eng_prob,
            "ml_mode": self.ml_mode,
        }

        sid = session_id if session_id is not None else "_default"
        pose_for_score, yaw0, pitch0 = self._centered_pose_buf(sid, pose_buf)
        features["pose_baseline_yaw"] = None if yaw0 is None else round(float(yaw0), 4)
        features["pose_baseline_pitch"] = (
            None if pitch0 is None else round(float(pitch0), 4)
        )
        features["fusion_threshold"] = float(self.fusion_threshold)

        if self.fusion_model is not None and len(gaze_buf) > 0 and len(pose_for_score) > 0:
            try:
                feat_vec = self.build_fusion_features(
                    list(gaze_buf),
                    list(pose_for_score),
                    eng_prob,
                    lm_buf=list(lm_buf) if lm_buf else None,
                    face_detected=bool(last_meta.get("face_detected", True)),
                )
                if hasattr(self.fusion_model, "predict_proba"):
                    proba = self.fusion_model.predict_proba(feat_vec)[0]
                    # Assume class 1 = distracted when binary
                    if len(proba) >= 2:
                        dist_prob = float(proba[1])
                    else:
                        dist_prob = float(proba[0])
                    raw_verdict = (
                        "DISTRACTED"
                        if dist_prob >= self.fusion_threshold
                        else "FOCUSED"
                    )
                else:
                    pred = self.fusion_model.predict(feat_vec)[0]
                    raw_verdict = "DISTRACTED" if int(pred) == 1 else "FOCUSED"
                    dist_prob = 1.0 if raw_verdict == "DISTRACTED" else 0.0
                # Temporal hysteresis for model6 (glances < enter window stay FOCUSED).
                # model5 keeps the instantaneous threshold decision for compatibility.
                if self.fusion_kind == "model6_mlp":
                    verdict = self._apply_hysteresis(sid, dist_prob)
                else:
                    verdict = raw_verdict
                conf = dist_prob if verdict == "DISTRACTED" else (1.0 - dist_prob)
                features["distract_prob"] = round(float(dist_prob), 4)
                features["raw_fusion_verdict"] = raw_verdict
                features["hysteresis_state"] = verdict
                features["inference_path"] = "fusion"
                features["fusion_kind"] = self.fusion_kind
                return verdict, float(conf), features
            except Exception as e:
                print(f"[MLService] Fusion scoring error: {e}")

        # Heuristic gate (same thresholds as webcam_test.py) when fusion unavailable.
        # Valid heuristic results remain FOCUSED/DISTRACTED (not UNKNOWN).
        features["inference_path"] = "heuristic"
        gaze_arr = np.array(gaze_buf, dtype=np.float32)
        pose_arr = np.array(pose_for_score, dtype=np.float32)
        p_c = float(np.mean(gaze_arr[:, 0]))
        p_l = float(np.mean(gaze_arr[:, 1]))
        p_r = float(np.mean(gaze_arr[:, 2]))
        p_d = float(np.mean(gaze_arr[:, 3]))
        gaze_away = (p_l + p_r + p_d) / max(p_c + p_l + p_r + p_d, 1e-8)
        yaw_mean = float(np.mean(pose_arr[:, 0]))
        pitch_mean = float(np.mean(pose_arr[:, 1]))

        if not last_meta.get("face_detected", True):
            # Usable decode but no face → UNKNOWN (not a valid classification).
            return "UNKNOWN", None, {
                **features,
                "reason": "no_face",
                "face_detected": False,
                "inference_path": "unusable",
                "confidence": None,
            }
        if gaze_away > 0.70 or abs(yaw_mean) > 25.0 or abs(pitch_mean) > 20.0:
            return "DISTRACTED", None, {
                **features,
                "gaze_away_ratio": round(gaze_away, 3),
                "reason": "heuristic_gate",
            }
        return "FOCUSED", None, {
            **features,
            "gaze_away_ratio": round(gaze_away, 3),
            "reason": "heuristic_gate",
        }

    @staticmethod
    def _unknown_result(reason: str, ml_mode: str, **extra) -> Tuple[str, Optional[float], dict]:
        """Explicit unusable observation — never fabricates focus or face_detected."""
        meta = {
            "reason": reason,
            "face_detected": None,
            "ml_mode": ml_mode,
            "inference_path": "unusable",
            **extra,
        }
        return "UNKNOWN", None, meta

    # ------------------------------------------------------------------
    # v3 live path: shared MediaPipe features → model6 v3 / rule → hysteresis
    # ------------------------------------------------------------------

    def _server_elapsed(self, session_id: Any) -> float:
        now = time.monotonic()
        with self._state_lock:
            t0 = self._session_t0.setdefault(session_id, now)
        return now - t0

    def _live_scorer_for(self, session_id: Any):
        with self._state_lock:
            scorer = self._live_scorers.get(session_id)
            if scorer is None:
                from models.src.features.live import LiveWindowScorer

                scorer = LiveWindowScorer(
                    window_sec=self.live_window_sec,
                    baseline_frames=self.live_baseline_frames,
                )
                self._live_scorers[session_id] = scorer
                self._session_locks[session_id] = threading.RLock()
            self._session_last_seen[session_id] = time.monotonic()
            return scorer, self._session_locks[session_id]

    def reap_idle_sessions(self, now: Optional[float] = None) -> List[Any]:
        """Free scorers/landmarkers of sessions that stopped sending heartbeats."""
        now = time.monotonic() if now is None else now
        with self._state_lock:
            idle = [
                sid
                for sid, seen in self._session_last_seen.items()
                if now - seen > self.session_idle_sec
            ]
        for sid in idle:
            print(f"[MLService] Reaping idle session {sid}")
            self.clear_session(sid)
        return idle

    def set_session_calibrating(self, session_id: Any, on: bool) -> None:
        """Tell the live scorer that the client is in the 10 s calibration screen."""
        if session_id is None or not self._live_available:
            return
        try:
            scorer, lock = self._live_scorer_for(session_id)
            with lock:
                if hasattr(scorer, "set_calibrating"):
                    scorer.set_calibrating(bool(on))
        except Exception as e:
            print(f"[MLService] set_session_calibrating error: {e}")

    def predict_frames(
        self,
        frames: List[Tuple[float, str]],
        session_id: Any = None,
    ) -> Tuple[str, Optional[float], dict]:
        """Score a heartbeat of timestamped frames ``[(t_sec, base64_jpeg), ...]``.

        Verdict is FOCUSED, DISTRACTED, or UNKNOWN (confidence None).
        """
        sid = session_id if session_id is not None else "_default"
        self.reap_idle_sessions()
        decoded = []
        for t_sec, image in frames:
            img = self._decode_frame(image)
            if img is not None and getattr(img, "size", 0) > 0:
                decoded.append((float(t_sec), img))
        if not decoded:
            return self._unknown_result("no_frame_data", self.ml_mode)
        if not self._live_available:
            return self._unknown_result("ml_unavailable", self.ml_mode)
        try:
            scorer, lock = self._live_scorer_for(sid)
            with lock:
                last = None
                for t_sec, img in sorted(decoded, key=lambda x: x[0]):
                    f = scorer.add_frame(t_sec, img)
                    if f is not None:
                        last = f
                if last is None:
                    return self._unknown_result("stale_frames", self.ml_mode)
                return self._decide_live(sid, scorer.features(), last)
        except Exception as e:
            print(f"[MLService] Live scoring error: {e}")
            return self._unknown_result("inference_exception", self.ml_mode, error=str(e))

    def _decide_live(self, sid: Any, feats: Optional[dict], last_frame) -> Tuple[str, Optional[float], dict]:
        face_now = bool(getattr(last_frame, "face_present", False))
        if feats is None:
            return self._unknown_result(
                "no_face" if not face_now else "warming_up",
                self.ml_mode,
                face_detected=face_now,
                face_box_px=None,
            )
        # Calibrating: withhold verdicts until baseline is locked.
        if feats.get("calibrating") or (
            not feats.get("baseline_locked") and feats.get("calibrating", False)
        ):
            return self._unknown_result(
                "calibrating", self.ml_mode, face_detected=face_now, face_box_px=None
            )
        if not feats.get("baseline_locked"):
            return self._unknown_result(
                "calibrating", self.ml_mode, face_detected=face_now, face_box_px=None
            )

        meta = {
            "ml_mode": self.ml_mode,
            "face_detected": face_now,
            "face_box_px": None,
            "window_features": {
                k: round(float(feats[k]), 4)
                for k in MODEL6_FEATURE_NAMES
                if k in feats
            },
            "baseline_locked": bool(feats.get("baseline_locked")),
            "n_frames": int(feats.get("n_frames", 0)),
            "window_end_ms": int(
                float(feats.get("window_end_sec", feats["window_start_sec"] + feats["window_sec"]))
                * 1000
            ),
        }
        t_now = float(feats.get("window_end_sec", feats["window_start_sec"] + feats["window_sec"]))
        face_ratio = float(feats.get("face_present_ratio", 0.0))
        body_ratio = float(feats.get("body_present_ratio", 0.0))

        # Default hysteresis for rule / body paths
        hyst = self.fusion_hysteresis or {
            "enter_prob": HYST_ENTER_PROB,
            "enter_sec": HYST_ENTER_SEC,
            "exit_prob": HYST_EXIT_PROB,
            "exit_sec": HYST_EXIT_SEC,
        }

        # Absent desk: no body for ≥10 s → DISTRACTED via hysteresis (source=absent).
        if body_ratio < BODY_PRESENT_RATIO and face_ratio < NO_FACE_RATIO:
            t0 = self._session_no_body_t0.get(sid)
            if t0 is None:
                self._session_no_body_t0[sid] = t_now
                t0 = t_now
            if (t_now - float(t0)) >= 10.0:
                verdict = self._apply_hysteresis(sid, 0.85, now=t_now, params=hyst)
                p = 0.85
                eng = round(1.0 - p, 4)
                return verdict, (p if verdict == "DISTRACTED" else 1.0 - p), {
                    **meta,
                    "reason": "absent",
                    "source": "absent",
                    "inference_path": "rule_absent",
                    "distract_prob": p,
                    "engagement_score": eng,
                    "confidence": round(p if verdict == "DISTRACTED" else 1.0 - p, 4),
                    "hysteresis_state": verdict,
                }
            # Still within grace: UNKNOWN, reset hysteresis timers
            self._session_hyst_high_t0[sid] = None
            self._session_hyst_low_t0[sid] = None
            return self._unknown_result("no_face", self.ml_mode, face_detected=False, face_box_px=None)
        self._session_no_body_t0[sid] = None

        # Partial face dropout: do NOT hand the window to the model as off-screen.
        if face_ratio < LOW_FACE_RATIO:
            if body_ratio >= BODY_PRESENT_RATIO:
                # body_no_face: p=0.7 through hysteresis (no instant DISTRACTED)
                verdict = self._apply_hysteresis(sid, 0.7, now=t_now, params=hyst)
                p = 0.7
                eng = round(1.0 - p, 4)
                return verdict, (p if verdict == "DISTRACTED" else 1.0 - p), {
                    **meta,
                    "reason": "body_no_face",
                    "source": "body_no_face",
                    "inference_path": "rule_body_no_face",
                    "distract_prob": p,
                    "engagement_score": eng,
                    "confidence": round(p if verdict == "DISTRACTED" else 1.0 - p, 4),
                    "hysteresis_state": verdict,
                }
            self._session_hyst_high_t0[sid] = None
            self._session_hyst_low_t0[sid] = None
            return self._unknown_result(
                "low_face", self.ml_mode, face_detected=face_now, face_box_px=None
            )

        if self._has_v3_pack():
            feat_names = list(self.fusion_feat_names) or list(MODEL6_FEATURE_NAMES)
            # v3 packs used head_roll_mean; v4 uses head_roll_dev — alias either way.
            feat_row = dict(feats)
            if "head_roll_dev" in feat_row and "head_roll_mean" not in feat_row:
                feat_row["head_roll_mean"] = feat_row["head_roll_dev"]
            if "head_roll_mean" in feat_row and "head_roll_dev" not in feat_row:
                feat_row["head_roll_dev"] = feat_row["head_roll_mean"]
            X = np.array([[float(feat_row.get(n, 0.0)) for n in feat_names]], dtype=np.float32)
            dist_prob = float(self.fusion_model.predict_proba(X)[0][1])
            threshold = float(self.fusion_threshold)
            hyst = self.fusion_hysteresis or hyst
            path = "fusion"
            source = "model6"
        else:
            from models.src.features.windows import distraction_proxy

            dist_prob = float(np.clip(distraction_proxy(feats) / 2.0, 0.0, 1.0))
            threshold = RULE_PROXY_THRESHOLD
            hyst = {
                "enter_prob": threshold,
                "enter_sec": HYST_ENTER_SEC,
                "exit_prob": threshold,
                "exit_sec": HYST_EXIT_SEC,
            }
            path = "rule_proxy"
            source = "rule"
        raw = "DISTRACTED" if dist_prob >= threshold else "FOCUSED"
        verdict = self._apply_hysteresis(sid, dist_prob, now=t_now, params=hyst)
        conf = dist_prob if verdict == "DISTRACTED" else 1.0 - dist_prob
        engagement = round(1.0 - dist_prob, 4)
        # Rolling re-baseline on the live scorer when confidently focused.
        try:
            scorer, _lock = self._live_scorer_for(sid)
            scorer.maybe_rebaseline(dist_prob, face_now)
        except Exception:
            pass
        return verdict, float(conf), {
            **meta,
            "inference_path": path,
            "source": source,
            "fusion_kind": self.fusion_kind if path == "fusion" else None,
            "fusion_threshold": threshold,
            "distract_prob": round(dist_prob, 4),
            "engagement_score": engagement,
            "raw_fusion_verdict": raw,
            "hysteresis_state": verdict,
            "confidence": round(float(conf), 4),
        }

    def predict_frame_image(
        self,
        image_base64: str,
        session_id: Any = None,
    ) -> Tuple[str, Optional[float], dict]:
        """
        Decode a base64 JPEG frame, run M1/M2/M4→M5 (or fallback), return verdict.

        Verdict is FOCUSED, DISTRACTED, or UNKNOWN. Confidence is None for UNKNOWN.
        """
        sid = session_id if session_id is not None else "_default"
        if self._uses_live_path():
            # Single-frame (old client) heartbeat: timestamp it with server time.
            return self.predict_frames([(self._server_elapsed(sid), image_base64)], session_id=sid)

        frame = self._decode_frame(image_base64)
        if frame is None or getattr(frame, "size", 0) == 0:
            return self._unknown_result("no_frame_data", self.ml_mode)

        try:
            # Face gate before buffer append: no-face frames must not pollute
            # the fusion window with whole-frame gaze / centre-crop pose.
            face_box = self._detect_face(frame)
            if face_box is None:
                # S3: person without Haar face → DISTRACTED (body_no_face).
                # Still do not append to the fusion buffer.
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                lm_body = self.extract_landmarks(frame_rgb, sid)
                if self._landmarks_indicate_person(lm_body):
                    return (
                        "DISTRACTED",
                        0.85,
                        {
                            "reason": "body_no_face",
                            "face_detected": False,
                            "face_box_px": None,
                            "ml_mode": self.ml_mode,
                            "inference_path": "body_no_face",
                            "confidence": 0.85,
                        },
                    )
                return self._unknown_result(
                    "no_face",
                    self.ml_mode,
                    face_detected=False,
                    face_box_px=None,
                )

            gaze_probs, pose_xyz, lm, meta = self._infer_frame_signals(
                frame, sid, face_box=face_box
            )
            # Re-check: keep defensive UNKNOWN if meta disagrees.
            if not meta.get("face_detected", False):
                return self._unknown_result(
                    "no_face",
                    self.ml_mode,
                    face_detected=False,
                    face_box_px=None,
                )

            self._update_pose_baseline(sid, pose_xyz)

            buf = self._session_bufs[sid]
            buf["gaze"].append(gaze_probs)
            buf["pose"].append(pose_xyz)
            buf["lm"].append(lm)

            # Score as soon as we have at least one frame; prefer window_size samples
            gaze_list = list(buf["gaze"])
            pose_list = list(buf["pose"])
            lm_list = list(buf["lm"])
            if len(gaze_list) > self.window_size:
                gaze_list = gaze_list[-self.window_size :]
                pose_list = pose_list[-self.window_size :]
                lm_list = lm_list[-self.window_size :]

            return self._score_window(
                gaze_list, pose_list, lm_list, meta, session_id=sid
            )
        except Exception as e:
            print(f"[MLService] Frame processing error: {e}")
            return self._unknown_result(
                "inference_exception",
                self.ml_mode,
                error=str(e),
            )

    def predict_window_features(self, features_dict: dict) -> Tuple[str, Optional[float]]:
        """
        Client-supplied feature path. Routes only accept it under TESTING
        (otherwise a client could report itself FOCUSED). Uses the same rule
        thresholds as before but never invents a confidence; anything it cannot
        evaluate is UNKNOWN.
        """
        try:
            if features_dict.get("face_detected", True) is False:
                return "UNKNOWN", None
            gaze_conf = float(features_dict["gaze_confidence"])
            engagement = float(features_dict["engagement_score"])
            head_yaw = abs(float(features_dict.get("head_pose_yaw", 0.0)))
        except (KeyError, TypeError, ValueError):
            return "UNKNOWN", None
        if gaze_conf < 0.40 or head_yaw > 25.0 or engagement < 0.35:
            return "DISTRACTED", None
        return "FOCUSED", None
