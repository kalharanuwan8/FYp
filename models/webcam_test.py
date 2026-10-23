"""
Real-time webcam distraction detection — Full Fusion Pipeline.

Every WINDOW_SEC seconds all 3 models vote:
  Model 1 · Gaze       → gaze direction probabilities (p_center/left/right/down)
  Model 2 · Head Pose  → yaw / pitch / roll (degrees)
  Model 4 · Engagement → body activity probability (active_work)

Their aggregated signals are fed into:
  Model 5 · Fusion     → final DISTRACTED / FOCUSED verdict + confidence

Usage:
    python webcam_test.py
    python webcam_test.py --window-sec 3 --camera 1
    python webcam_test.py --gaze-ckpt path/to/gaze.pt

Controls:
    q  - quit
    s  - save screenshot
"""
from __future__ import annotations

import argparse
import time
from collections import deque
from pathlib import Path

import cv2
import joblib
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms as T, models
from torchvision.models import mobilenet_v2, MobileNet_V2_Weights


# ─── Face / Eye detector (OpenCV Haar — ships with OpenCV, no download needed) ─
_FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_EYE_CASCADE  = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")


def detect_eye_crop(frame_bgr: np.ndarray):
    """Detect face → largest eye crop (grayscale). Returns (crop, rect) or (None, None)."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    faces = _FACE_CASCADE.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
    if len(faces) == 0:
        return None, None
    fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
    face_gray = gray[fy:fy + fh, fx:fx + fw]
    eyes = _EYE_CASCADE.detectMultiScale(face_gray, 1.1, 5, minSize=(20, 20))
    if len(eyes) == 0:
        return face_gray[:fh // 2, :], (fx, fy, fw, fh // 2)
    ex, ey, ew, eh = max(eyes, key=lambda r: r[2] * r[3])
    return face_gray[ey:ey + eh, ex:ex + ew], (fx + ex, fy + ey, ew, eh)


def detect_face_crop(frame_bgr: np.ndarray) -> np.ndarray:
    """Return face crop (BGR) with padding, or central 60% fallback."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    faces = _FACE_CASCADE.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
    if len(faces) > 0:
        fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
        pad = int(fw * 0.15)
        x1 = max(0, fx - pad); y1 = max(0, fy - pad)
        x2 = min(frame_bgr.shape[1], fx + fw + pad)
        y2 = min(frame_bgr.shape[0], fy + fh + pad)
        return frame_bgr[y1:y2, x1:x2]
    h, w = frame_bgr.shape[:2]
    cw, ch = int(w * 0.6), int(h * 0.6)
    x1 = (w - cw) // 2; y1 = (h - ch) // 2
    return frame_bgr[y1:y1 + ch, x1:x1 + cw]


# ─── MediaPipe body pose (for Model 4 engagement) ────────────────────────────
_MP_AVAILABLE = False
_pose_landmarker = None

def _try_init_mediapipe():
    global _MP_AVAILABLE, _pose_landmarker
    try:
        import mediapipe as mp
        BaseOptions = mp.tasks.BaseOptions
        PoseLandmarker = mp.tasks.vision.PoseLandmarker
        PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        task_path = Path("src/model4_engagement/pose_landmarker_lite.task")
        if not task_path.exists():
            print(f"  [WARN] MediaPipe task file not found: {task_path}")
            return
        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(task_path)),
            running_mode=VisionRunningMode.VIDEO,
            min_pose_detection_confidence=0.5,
        )
        _pose_landmarker = PoseLandmarker.create_from_options(options)
        _MP_AVAILABLE = True
        print("  ✓ MediaPipe PoseLandmarker loaded (engagement features active)")
    except Exception as e:
        print(f"  [WARN] MediaPipe unavailable ({e}). Engagement score will be 0.5")

# Landmark indices (MediaPipe 33-point model)
_LM_IDX = {"nose": 0, "l_shoulder": 11, "r_shoulder": 12,
            "l_elbow": 13, "r_elbow": 14, "l_wrist": 15, "r_wrist": 16}

def extract_landmarks(frame_rgb: np.ndarray, timestamp_ms: int) -> dict | None:
    """Run MediaPipe on one frame; return landmark dict or None."""
    if not _MP_AVAILABLE or _pose_landmarker is None:
        return None
    try:
        import mediapipe as mp
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = _pose_landmarker.detect_for_video(mp_img, timestamp_ms)
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


def _safe_nanmean(arr):
    return float(np.nanmean(arr)) if len(arr) > 0 else 0.0

def _safe_nanstd(arr):
    return float(np.nanstd(arr)) if len(arr) > 0 else 0.0

def compute_engagement_features(lm_buf: list[dict | None]) -> dict:
    """Compute Model 4 feature vector from a list of per-frame landmark dicts."""
    valid = [lm for lm in lm_buf if lm is not None]
    n = len(valid)
    pose_ratio = n / max(len(lm_buf), 1)

    def col(name, axis):
        return np.array([lm[f"{name}_{axis}"] for lm in valid], dtype=float)

    if n < 4:
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
    lw_xy   = np.stack([col("l_wrist", "x"), col("l_wrist", "y")], axis=1)
    rw_xy   = np.stack([col("r_wrist", "x"), col("r_wrist", "y")], axis=1)
    ls_xy   = np.stack([col("l_shoulder", "x"), col("l_shoulder", "y")], axis=1)
    rs_xy   = np.stack([col("r_shoulder", "x"), col("r_shoulder", "y")], axis=1)

    sh_mid = np.nanmean(np.stack([ls_xy, rs_xy], axis=0), axis=0)

    def speed(xy):
        d = np.diff(xy, axis=0)
        return np.sqrt(d[:, 0]**2 + d[:, 1]**2)

    lw_sp = speed(lw_xy); rw_sp = speed(rw_xy)
    lw_nose = np.sqrt(np.nansum((lw_xy - nose_xy)**2, axis=1))
    rw_nose = np.sqrt(np.nansum((rw_xy - nose_xy)**2, axis=1))
    lw_sh   = np.sqrt(np.nansum((lw_xy - sh_mid)**2, axis=1))
    rw_sh   = np.sqrt(np.nansum((rw_xy - sh_mid)**2, axis=1))
    nose_jitter = float(np.nanmean(np.nanstd(nose_xy, axis=0)))
    sh_y = sh_mid[:, 1]
    lw_below = float(np.nanmean(lw_xy[:, 1] > sh_y))
    rw_below = float(np.nanmean(rw_xy[:, 1] > sh_y))

    return {
        "pose_ratio": pose_ratio,
        "lw_speed_mean": _safe_nanmean(lw_sp), "lw_speed_std": _safe_nanstd(lw_sp),
        "rw_speed_mean": _safe_nanmean(rw_sp), "rw_speed_std": _safe_nanstd(rw_sp),
        "lw_to_nose_mean": _safe_nanmean(lw_nose), "rw_to_nose_mean": _safe_nanmean(rw_nose),
        "lw_to_sh_mean": _safe_nanmean(lw_sh), "rw_to_sh_mean": _safe_nanmean(rw_sh),
        "nose_jitter": nose_jitter,
        "lw_below_sh_ratio": lw_below, "rw_below_sh_ratio": rw_below,
    }


# ─── Gaze model ───────────────────────────────────────────────────────────────
GAZE_LABELS = {0: "center", 1: "left", 2: "right", 3: "down"}

def _build_gaze_model(num_classes=4):
    m = mobilenet_v2(weights=None)
    m.classifier[1] = nn.Linear(m.classifier[1].in_features, num_classes)
    return m

def _build_gaze_tf(img_size=224):
    return T.Compose([
        T.Resize((img_size, img_size)),
        T.ToTensor(),
        T.Lambda(lambda x: x.repeat(3, 1, 1) if x.shape[0] == 1 else x),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

@torch.no_grad()
def load_gaze_model(ckpt_path: Path, device: str):
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    m = _build_gaze_model(num_classes=ckpt["num_classes"]).to(device)
    m.load_state_dict(ckpt["model_state"])
    m.eval()
    return m, ckpt.get("img_size", 224)


# ─── Pose model ───────────────────────────────────────────────────────────────
def _build_pose_model():
    m = models.resnet18(weights=None)
    m.fc = nn.Linear(m.fc.in_features, 3)
    return m

def _build_pose_tf(img_size=224):
    return T.Compose([
        T.Resize((img_size, img_size)),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

@torch.no_grad()
def load_pose_model(ckpt_path: Path, device: str):
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    m = _build_pose_model().to(device)
    state = {k.replace("net.", ""): v for k, v in ckpt["model"].items()}
    m.load_state_dict(state)
    m.eval()
    return m


# ─── Engagement model (sklearn) ───────────────────────────────────────────────
def load_engagement_model(ckpt_path: Path):
    pack = joblib.load(ckpt_path)
    return pack["model"], pack["feature_cols"]


# ─── Fusion model (sklearn) ───────────────────────────────────────────────────
FUSION_FEATURES_DEFAULT = [
    "p_center_mean", "p_left_mean", "p_right_mean", "p_down_mean",
    "gaze_away_ratio",
    "yaw_mean", "pitch_mean", "roll_mean",
    "yaw_std", "pitch_std", "roll_std",
    "engagement_prob_mean",
]

def load_fusion_model(ckpt_path: Path):
    pack = joblib.load(ckpt_path)
    return pack["model"], float(pack.get("threshold", 0.5)), pack.get("features", FUSION_FEATURES_DEFAULT)


# ─── Window aggregation → fusion feature vector ───────────────────────────────
def build_fusion_features(
    gaze_buf: list,
    pose_buf: list,
    eng_prob: float,
    feature_names: list[str],
) -> np.ndarray:
    """Build fusion feature vector matching exactly the trained model's feature list."""
    gaze_arr = np.array(gaze_buf, dtype=np.float32)   # (T, 4)
    pose_arr = np.array(pose_buf, dtype=np.float32)   # (T, 3)

    p_c = float(np.mean(gaze_arr[:, 0]))
    p_l = float(np.mean(gaze_arr[:, 1]))
    p_r = float(np.mean(gaze_arr[:, 2]))
    p_d = float(np.mean(gaze_arr[:, 3]))
    gaze_away = (p_l + p_r + p_d) / max(p_c + p_l + p_r + p_d, 1e-8)

    yaw_mean   = float(np.mean(pose_arr[:, 0]))
    pitch_mean = float(np.mean(pose_arr[:, 1]))
    roll_mean  = float(np.mean(pose_arr[:, 2]))
    yaw_std    = float(np.std(pose_arr[:, 0]))
    pitch_std  = float(np.std(pose_arr[:, 1]))
    roll_std   = float(np.std(pose_arr[:, 2]))

    all_vals = {
        "p_center_mean": p_c, "p_left_mean": p_l,
        "p_right_mean": p_r, "p_down_mean": p_d,
        "gaze_away_ratio": gaze_away,
        "yaw_mean": yaw_mean, "pitch_mean": pitch_mean, "roll_mean": roll_mean,
        "yaw_std": yaw_std, "pitch_std": pitch_std, "roll_std": roll_std,
        "engagement_prob_mean": eng_prob,
    }

    # Build vector using ONLY the features the trained model expects
    feat_vec = np.array(
        [all_vals.get(f, 0.0) for f in feature_names],
        dtype=np.float32
    ).reshape(1, -1)
    return feat_vec


# ─── Drawing helpers ─────────────────────────────────────────────────────────
COLOR_GREEN  = (0, 220, 80)
COLOR_RED    = (0, 60, 255)
COLOR_YELLOW = (0, 220, 255)
COLOR_WHITE  = (255, 255, 255)
COLOR_BG     = (20, 20, 30)
COLOR_PANEL  = (35, 35, 50)

def draw_bar(frame, label, val, x, y, w=180, h=12, color=COLOR_GREEN):
    cv2.rectangle(frame, (x, y), (x + w, y + h), (60, 60, 70), -1)
    cv2.rectangle(frame, (x, y), (x + int(w * val), y + h), color, -1)
    cv2.putText(frame, f"{label}: {val:.0%}", (x + w + 6, y + h),
                cv2.FONT_HERSHEY_SIMPLEX, 0.36, (180, 180, 180), 1, cv2.LINE_AA)

def draw_panel(frame, gaze_label, gaze_conf, yaw, pitch, roll,
               verdict, verdict_prob, countdown, window_sec, fps,
               eng_prob, face_detected, is_calibrated, calibrating):
    h, w = frame.shape[:2]
    panel_w = 300

    # Semi-transparent background panel
    overlay = frame.copy()
    cv2.rectangle(overlay, (8, 8), (panel_w, 460), COLOR_PANEL, -1)
    cv2.addWeighted(overlay, 0.80, frame, 0.20, 0, frame)

    # Title
    cv2.putText(frame, "DISTRACTION MONITOR", (18, 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_WHITE, 1, cv2.LINE_AA)
    cv2.line(frame, (18, 44), (panel_w - 10, 44), (80, 80, 100), 1)

    # Face detection indicator
    fd_color = COLOR_GREEN if face_detected else COLOR_RED
    fd_text = f"Face: {'detected' if face_detected else 'NOT FOUND'}"
    if calibrating > 0:
        fd_text = f"CALIBRATING... {calibrating}"
        fd_color = COLOR_YELLOW
    cv2.putText(frame, fd_text, (18, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.42, fd_color, 1, cv2.LINE_AA)

    if is_calibrated and calibrating == 0:
        cv2.putText(frame, "[Calibrated]", (180, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.42, COLOR_GREEN, 1, cv2.LINE_AA)

    # ── Per-frame signals ──
    cv2.putText(frame, "Live signals", (18, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (140, 140, 180), 1, cv2.LINE_AA)

    # Gaze
    g_col = COLOR_GREEN if gaze_label == "center" else COLOR_YELLOW
    cv2.putText(frame, f"Gaze: {gaze_label.upper():<7}", (18, 112),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, g_col, 1, cv2.LINE_AA)
    draw_bar(frame, "conf", gaze_conf, 18, 118, color=g_col)

    # Head pose
    pose_items = [("Yaw", yaw, 30), ("Pitch", pitch, 25), ("Roll", roll, 35)]
    for i, (name, val, thr) in enumerate(pose_items):
        col = COLOR_RED if abs(val) > thr else COLOR_GREEN
        cv2.putText(frame, f"  {name}: {val:+.1f} deg", (18, 150 + i * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.43, col, 1, cv2.LINE_AA)

    # Engagement
    draw_bar(frame, "Engagement", eng_prob, 18, 228, color=COLOR_GREEN)

    # ── Fusion verdict ──
    cv2.line(frame, (18, 255), (panel_w - 10, 255), (80, 80, 100), 1)
    cv2.putText(frame, "Window verdict (Heuristics)", (18, 274),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (140, 140, 180), 1, cv2.LINE_AA)

    v_text  = verdict if verdict else "Collecting..."
    v_color = COLOR_RED if verdict == "DISTRACTED" else (COLOR_GREEN if verdict == "FOCUSED" else COLOR_YELLOW)
    cv2.putText(frame, v_text, (18, 306),
                cv2.FONT_HERSHEY_SIMPLEX, 0.80, v_color, 2, cv2.LINE_AA)

    if verdict_prob is not None:
        draw_bar(frame, "distract prob", verdict_prob, 18, 316,
                 color=COLOR_RED if verdict_prob > 0.5 else COLOR_GREEN)

    # Countdown bar
    progress = 1.0 - (countdown / window_sec)
    cv2.putText(frame, f"Next verdict in {countdown:.1f}s", (18, 356),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (140, 140, 180), 1, cv2.LINE_AA)
    draw_bar(frame, "", progress, 18, 362, color=(100, 160, 255))

    # FPS
    cv2.putText(frame, f"FPS: {fps:.0f}", (w - 100, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (140, 140, 180), 1, cv2.LINE_AA)

    return frame


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Full fusion webcam distraction detector")
    ap.add_argument("--gaze-ckpt",       default="outputs/checkpoints/model1_gaze/best.pt")
    ap.add_argument("--pose-ckpt",       default="outputs/checkpoints/model2_pose/best.pt")
    ap.add_argument("--eng-ckpt",        default="outputs/checkpoints/model4_engagement/model.pkl")
    ap.add_argument("--camera",          type=int, default=0)
    ap.add_argument("--window-sec",      type=float, default=3.0,
                    help="Seconds of data per window (default: 3.0)")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    # Load models
    print("Loading gaze model...")
    gaze_model, gaze_img_size = load_gaze_model(Path(args.gaze_ckpt), device)
    gaze_tf = _build_gaze_tf(gaze_img_size)
    print("  ✓ Gaze model loaded")

    print("Loading pose model...")
    pose_model = load_pose_model(Path(args.pose_ckpt), device)
    pose_tf = _build_pose_tf()
    print("  ✓ Pose model loaded")

    print("Loading engagement model...")
    eng_model, eng_feature_cols = load_engagement_model(Path(args.eng_ckpt))
    print("  ✓ Engagement model loaded")

    print("  ✓ Manual Logic Gate Active (bypassing Model 5)")

    print("Initializing MediaPipe...")
    _try_init_mediapipe()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"Error: could not open camera {args.camera}")
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    fps_cam = cap.get(cv2.CAP_PROP_FPS) or 30.0
    window_frames = max(10, int(args.window_sec * fps_cam))

    print(f"\n--- Webcam distraction detector started (window = {args.window_sec}s) ---")
    print("Press 'q' to quit, 's' to save screenshot")
    print("Press 'c' to CALIBRATE (look at the center of your screen for 1 second)\n")

    # Rolling buffers — collect window_frames per window
    gaze_buf: list[np.ndarray] = []
    pose_buf: list[list]       = []
    lm_buf:   list[dict | None] = []

    verdict       = None
    verdict_prob  = None
    screenshot_dir = Path("screenshots")
    frame_count    = 0
    prev_time      = time.time()
    eng_prob       = 0.5  # last computed engagement prob
    t0             = time.time()

    # --- Calibration state ---
    calibrating = 0
    calib_frames_total = int(fps_cam * 1.0)  # ~1 second of frames
    baseline_gaze_logits = np.zeros(4, dtype=np.float32)
    baseline_pose = np.zeros(3, dtype=np.float32)
    accum_gaze_logits = np.zeros(4, dtype=np.float32)
    accum_pose = np.zeros(3, dtype=np.float32)
    is_calibrated = False

    with torch.no_grad():
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame")
                break

            frame_count += 1
            timestamp_ms = int((time.time() - t0) * 1000)
            face_detected = False

            # ── Gaze inference ──────────────────────────────────────────────
            eye_crop, _ = detect_eye_crop(frame)
            if eye_crop is not None:
                face_detected = True
                img_gray = Image.fromarray(eye_crop).convert("L")
            else:
                img_gray = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("L")

            x_gaze = gaze_tf(img_gray).unsqueeze(0).to(device)
            raw_gaze_logits = gaze_model(x_gaze).squeeze(0).cpu().numpy()

            # ── Pose inference ───────────────────────────────────────────────
            roi_bgr = detect_face_crop(frame)
            roi_rgb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB)
            pil_rgb = Image.fromarray(roi_rgb).convert("RGB")
            x_pose  = pose_tf(pil_rgb).unsqueeze(0).to(device)
            raw_pose = pose_model(x_pose).squeeze(0).cpu().numpy()

            # ── Calibration Logic ────────────────────────────────────────────
            if calibrating > 0:
                accum_gaze_logits += raw_gaze_logits
                accum_pose += raw_pose
                calibrating -= 1
                if calibrating == 0:
                    baseline_gaze_logits = accum_gaze_logits / calib_frames_total
                    baseline_pose = accum_pose / calib_frames_total
                    is_calibrated = True
                    print(f"\n[Calibration Done] Gaze baseline: {baseline_gaze_logits}")
                    print(f"[Calibration Done] Pose baseline: {baseline_pose}\n")

            # Adjust with baseline
            adj_gaze_logits = raw_gaze_logits - baseline_gaze_logits
            if is_calibrated:
                adj_gaze_logits[0] += 2.0  # Boost 'center' logit when near baseline
                
            # Compute calibrated softmax for UI display and heuristics
            exp_logits = np.exp(adj_gaze_logits - np.max(adj_gaze_logits))
            adj_gaze_probs = exp_logits / exp_logits.sum()

            gaze_idx   = int(adj_gaze_probs.argmax())
            gaze_label = GAZE_LABELS[gaze_idx]
            gaze_conf  = float(adj_gaze_probs[gaze_idx])

            adj_pose = raw_pose - baseline_pose
            yaw, pitch, roll = float(adj_pose[0]), float(adj_pose[1]), float(adj_pose[2])

            # ── MediaPipe body landmarks ─────────────────────────────────────
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            lm = extract_landmarks(frame_rgb, timestamp_ms)

            # ── Accumulate into window buffers ───────────────────────────────
            gaze_buf.append(adj_gaze_probs.copy())
            pose_buf.append([yaw, pitch, roll])
            lm_buf.append(lm)

            # ── When window is full → run fusion ─────────────────────────────
            if len(gaze_buf) >= window_frames:
                # Engagement features from body landmarks
                eng_feats = compute_engagement_features(lm_buf)
                eng_X = np.array([[eng_feats.get(c, 0.0) for c in eng_feature_cols]],
                                  dtype=np.float32)
                eng_prob = float(eng_model.predict_proba(eng_X)[0, 1])

                # ── Manual Logic Gate (Hacky Way) ──
                gaze_arr = np.array(gaze_buf, dtype=np.float32)
                pose_arr = np.array(pose_buf, dtype=np.float32)

                p_c = float(np.mean(gaze_arr[:, 0]))
                p_l = float(np.mean(gaze_arr[:, 1]))
                p_r = float(np.mean(gaze_arr[:, 2]))
                p_d = float(np.mean(gaze_arr[:, 3]))
                gaze_away = (p_l + p_r + p_d) / max(p_c + p_l + p_r + p_d, 1e-8)

                yaw_mean = float(np.mean(pose_arr[:, 0]))
                pitch_mean = float(np.mean(pose_arr[:, 1]))

                is_distracted = False
                distract_reason = ""

                if gaze_away > 0.70:
                    is_distracted = True
                    distract_reason = "Gaze Away"
                elif abs(yaw_mean) > 25.0:
                    is_distracted = True
                    distract_reason = "Looking sideways"
                elif abs(pitch_mean) > 20.0:
                    is_distracted = True
                    distract_reason = "Looking up/down"
                elif eng_prob < 0.20:
                    # Optional: flag low engagement
                    pass

                if is_distracted:
                    dist_prob = 1.0
                    verdict = "DISTRACTED"
                else:
                    dist_prob = 0.0
                    verdict = "FOCUSED"

                print(f"[Window] gaze_away={gaze_away:.2f}  "
                      f"yaw={yaw_mean:.1f} pitch={pitch_mean:.1f} eng={eng_prob:.2f}  "
                      f"→ {verdict} {f'({distract_reason})' if is_distracted else ''}")

                # Slide window by half
                half = window_frames // 2
                gaze_buf = gaze_buf[half:]
                pose_buf = pose_buf[half:]
                lm_buf   = lm_buf[half:]

            # ── FPS ──────────────────────────────────────────────────────────
            curr_time = time.time()
            fps = 1.0 / max(curr_time - prev_time, 1e-6)
            prev_time = curr_time

            # Countdown to next verdict
            frames_remaining = window_frames - len(gaze_buf)
            countdown = frames_remaining / max(fps_cam, 1.0)

            # ── Draw overlay ─────────────────────────────────────────────────
            frame = draw_panel(
                frame, gaze_label, gaze_conf,
                yaw, pitch, roll,
                verdict, verdict_prob,
                countdown, args.window_sec, fps,
                eng_prob, face_detected, is_calibrated, calibrating
            )

            cv2.imshow("Distraction Detector — Full Fusion", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("c"):
                calibrating = calib_frames_total
                accum_gaze_logits = np.zeros(4, dtype=np.float32)
                accum_pose = np.zeros(3, dtype=np.float32)
                print("\n[Calibrating...] Please look at the center of your screen.")
            elif key == ord("s"):
                screenshot_dir.mkdir(exist_ok=True)
                fname = screenshot_dir / f"screenshot_{frame_count:06d}.png"
                cv2.imwrite(str(fname), frame)
                print(f"Screenshot saved: {fname}")

    cap.release()
    if _pose_landmarker is not None:
        _pose_landmarker.close()
    cv2.destroyAllWindows()
    print("Done.")


if __name__ == "__main__":
    main()
