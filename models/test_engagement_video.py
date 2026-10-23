"""
Test Model 4 (Engagement) on a pre-recorded video.
"""
from __future__ import annotations

import argparse
import time
from collections import deque
from pathlib import Path

import cv2
import joblib
import numpy as np

# ─── MediaPipe body pose ──────────────────────────────────────────────────────
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
            return False
        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(task_path)),
            running_mode=VisionRunningMode.VIDEO,
            min_pose_detection_confidence=0.5,
        )
        _pose_landmarker = PoseLandmarker.create_from_options(options)
        _MP_AVAILABLE = True
        return True
    except Exception as e:
        print(f"  [WARN] MediaPipe unavailable ({e}).")
        return False

_LM_IDX = {"nose": 0, "l_shoulder": 11, "r_shoulder": 12,
            "l_elbow": 13, "r_elbow": 14, "l_wrist": 15, "r_wrist": 16}

def extract_landmarks(frame_rgb: np.ndarray, timestamp_ms: int) -> dict | None:
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
                out[f"{name}_x"], out[f"{name}_y"], out[f"{name}_vis"] = float("nan"), float("nan"), float("nan")
        return out
    except Exception:
        return None

def _safe_nanmean(arr): return float(np.nanmean(arr)) if len(arr) > 0 else 0.0
def _safe_nanstd(arr): return float(np.nanstd(arr)) if len(arr) > 0 else 0.0

def compute_engagement_features(lm_buf: list[dict | None]) -> dict:
    valid = [lm for lm in lm_buf if lm is not None]
    n = len(valid)
    pose_ratio = n / max(len(lm_buf), 1)

    def col(name, axis): return np.array([lm[f"{name}_{axis}"] for lm in valid], dtype=float)

    if n < 4:
        return {
            "pose_ratio": pose_ratio, "lw_speed_mean": 0.0, "lw_speed_std": 0.0,
            "rw_speed_mean": 0.0, "rw_speed_std": 0.0, "lw_to_nose_mean": 0.5,
            "rw_to_nose_mean": 0.5, "lw_to_sh_mean": 0.3, "rw_to_sh_mean": 0.3,
            "nose_jitter": 0.0, "lw_below_sh_ratio": 0.5, "rw_below_sh_ratio": 0.5,
        }

    nose_xy = np.stack([col("nose", "x"), col("nose", "y")], axis=1)
    lw_xy = np.stack([col("l_wrist", "x"), col("l_wrist", "y")], axis=1)
    rw_xy = np.stack([col("r_wrist", "x"), col("r_wrist", "y")], axis=1)
    ls_xy = np.stack([col("l_shoulder", "x"), col("l_shoulder", "y")], axis=1)
    rs_xy = np.stack([col("r_shoulder", "x"), col("r_shoulder", "y")], axis=1)

    sh_mid = np.nanmean(np.stack([ls_xy, rs_xy], axis=0), axis=0)

    def speed(xy):
        d = np.diff(xy, axis=0)
        return np.sqrt(d[:, 0]**2 + d[:, 1]**2)

    lw_sp, rw_sp = speed(lw_xy), speed(rw_xy)
    lw_nose = np.sqrt(np.nansum((lw_xy - nose_xy)**2, axis=1))
    rw_nose = np.sqrt(np.nansum((rw_xy - nose_xy)**2, axis=1))
    lw_sh = np.sqrt(np.nansum((lw_xy - sh_mid)**2, axis=1))
    rw_sh = np.sqrt(np.nansum((rw_xy - sh_mid)**2, axis=1))
    nose_jitter = float(np.nanmean(np.nanstd(nose_xy, axis=0)))
    sh_y = sh_mid[:, 1]
    lw_below = float(np.nanmean(lw_xy[:, 1] > sh_y))
    rw_below = float(np.nanmean(rw_xy[:, 1] > sh_y))

    return {
        "pose_ratio": pose_ratio, "lw_speed_mean": _safe_nanmean(lw_sp), "lw_speed_std": _safe_nanstd(lw_sp),
        "rw_speed_mean": _safe_nanmean(rw_sp), "rw_speed_std": _safe_nanstd(rw_sp),
        "lw_to_nose_mean": _safe_nanmean(lw_nose), "rw_to_nose_mean": _safe_nanmean(rw_nose),
        "lw_to_sh_mean": _safe_nanmean(lw_sh), "rw_to_sh_mean": _safe_nanmean(rw_sh),
        "nose_jitter": nose_jitter, "lw_below_sh_ratio": lw_below, "rw_below_sh_ratio": rw_below,
    }

# ─── Engagement model (sklearn) ───────────────────────────────────────────────
def load_engagement_model(ckpt_path: Path):
    pack = joblib.load(ckpt_path)
    return pack["model"], pack["feature_cols"]

# ─── Drawing helpers ─────────────────────────────────────────────────────────
COLOR_GREEN = (0, 220, 80)
COLOR_WHITE = (255, 255, 255)
COLOR_PANEL = (35, 35, 50)

def draw_bar(frame, label, val, x, y, w=180, h=12, color=COLOR_GREEN):
    cv2.rectangle(frame, (x, y), (x + w, y + h), (60, 60, 70), -1)
    cv2.rectangle(frame, (x, y), (x + int(w * val), y + h), color, -1)
    cv2.putText(frame, f"{label}: {val:.0%}", (x + w + 6, y + h),
                cv2.FONT_HERSHEY_SIMPLEX, 0.36, (180, 180, 180), 1, cv2.LINE_AA)

def draw_ui(frame, eng_prob, has_lm, fps):
    h, w = frame.shape[:2]
    panel_w = 300
    panel_h = 130

    overlay = frame.copy()
    cv2.rectangle(overlay, (8, 8), (panel_w, panel_h), COLOR_PANEL, -1)
    cv2.addWeighted(overlay, 0.80, frame, 0.20, 0, frame)

    cv2.putText(frame, "MODEL 4: ENGAGEMENT / POSTURE", (18, 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.50, COLOR_WHITE, 1, cv2.LINE_AA)
    cv2.line(frame, (18, 44), (panel_w - 10, 44), (80, 80, 100), 1)

    cv2.putText(frame, f"Tracking: {'Subject found' if has_lm else 'None'}",
                (18, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.42, COLOR_GREEN if has_lm else (100,100,100), 1, cv2.LINE_AA)

    draw_bar(frame, "Engagement Prob", eng_prob, 18, 90, w=200, color=COLOR_GREEN)

    cv2.putText(frame, f"FPS: {fps:.0f}", (w - 100, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (140, 140, 180), 1, cv2.LINE_AA)
    
    return frame

def draw_landmarks(frame, lm, color=(255, 150, 0)):
    if not lm: return
    h, w = frame.shape[:2]
    # Draw simple skeleton lines for demonstration
    pts = {}
    for name in _LM_IDX.keys():
        if not np.isnan(lm[f"{name}_x"]):
            pts[name] = (int(lm[f"{name}_x"] * w), int(lm[f"{name}_y"] * h))

    connections = [
        ("nose", "l_shoulder"), ("nose", "r_shoulder"), 
        ("l_shoulder", "r_shoulder"), ("l_shoulder", "l_elbow"), 
        ("r_shoulder", "r_elbow"), ("l_elbow", "l_wrist"), ("r_elbow", "r_wrist")
    ]
    for p1, p2 in connections:
        if p1 in pts and p2 in pts:
            cv2.line(frame, pts[p1], pts[p2], color, 2, cv2.LINE_AA)
    
    for pt in pts.values():
        cv2.circle(frame, pt, 4, (0, 255, 255), -1, cv2.LINE_AA)

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to input video file")
    ap.add_argument("--output", default="outputs/annotated_videos/eng_out.mp4", help="Path to save annotated video")
    ap.add_argument("--eng-ckpt", default="outputs/checkpoints/model4_engagement/model.pkl")
    ap.add_argument("--window-sec", type=float, default=2.5)
    args = ap.parse_args()

    print("Initializing MediaPipe...")
    if not _try_init_mediapipe():
        print("Failed to initialize mediapipe. Exiting.")
        return

    print("Loading Engagement model...")
    eng_model, eng_feature_cols = load_engagement_model(Path(args.eng_ckpt))
    print("✓ Model loaded successfully")

    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        print(f"Error: could not open video {args.input}")
        return

    fps_in = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    out_dir = Path(args.output).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(args.output, fourcc, fps_in, (width, height))

    print(f"Processing video: {args.input}")
    
    window_frames = max(10, int(args.window_sec * fps_in))
    lm_buf = []
    
    frame_count = 0
    eng_prob = 0.5
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        t_start = time.time()
        
        # Calculate timestamp for MediaPipe based on video frame rate
        timestamp_ms = int((frame_count / fps_in) * 1000)
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        lm = extract_landmarks(frame_rgb, timestamp_ms)
        lm_buf.append(lm)
        
        if len(lm_buf) > window_frames:
            lm_buf.pop(0)
            
        if len(lm_buf) == window_frames:
            eng_feats = compute_engagement_features(lm_buf)
            eng_X = np.array([[eng_feats.get(c, 0.0) for c in eng_feature_cols]], dtype=np.float32)
            eng_prob = float(eng_model.predict_proba(eng_X)[0, 1])

        t_end = time.time()
        fps = 1.0 / max(t_end - t_start, 1e-6)

        draw_landmarks(frame, lm)
        frame = draw_ui(frame, eng_prob, bool(lm), fps)
        
        out.write(frame)
        cv2.imshow("Model 4 - Engagement Testing", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    out.release()
    if _pose_landmarker is not None:
        _pose_landmarker.close()
    cv2.destroyAllWindows()
    print(f"Done! Processed {frame_count} frames. Video saved to {args.output}")

if __name__ == "__main__":
    main()
