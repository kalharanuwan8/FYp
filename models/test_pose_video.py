"""
Test Model 2 (Pose) on a pre-recorded video.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms as T, models
from torchvision.models import resnet18

# ─── Face detector (OpenCV Haar) ──────────────────────────────────────────────
_FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

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

# ─── Drawing helpers ─────────────────────────────────────────────────────────
COLOR_GREEN = (0, 220, 80)
COLOR_RED = (0, 60, 255)
COLOR_WHITE = (255, 255, 255)
COLOR_PANEL = (35, 35, 50)

def draw_ui(frame, yaw, pitch, roll, face_detected, fps):
    h, w = frame.shape[:2]
    panel_w = 300
    panel_h = 180

    overlay = frame.copy()
    cv2.rectangle(overlay, (8, 8), (panel_w, panel_h), COLOR_PANEL, -1)
    cv2.addWeighted(overlay, 0.80, frame, 0.20, 0, frame)

    cv2.putText(frame, "MODEL 2: HEAD POSE", (18, 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_WHITE, 1, cv2.LINE_AA)
    cv2.line(frame, (18, 44), (panel_w - 10, 44), (80, 80, 100), 1)

    fd_color = COLOR_GREEN if face_detected else COLOR_RED
    cv2.putText(frame, f"Face: {'detected' if face_detected else 'NOT FOUND'}",
                (18, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.42, fd_color, 1, cv2.LINE_AA)

    pose_items = [("Yaw", yaw, 30), ("Pitch", pitch, 25), ("Roll", roll, 35)]
    for i, (name, val, thr) in enumerate(pose_items):
        col = COLOR_RED if val is not None and abs(val) > thr else COLOR_GREEN
        val_str = f"{val:+.1f} deg" if val is not None else "N/A"
        cv2.putText(frame, f"  {name}: {val_str}", (18, 96 + i * 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2, cv2.LINE_AA)

    cv2.putText(frame, f"FPS: {fps:.0f}", (w - 100, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (140, 140, 180), 1, cv2.LINE_AA)
    return frame

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to input video file")
    ap.add_argument("--output", default="outputs/annotated_videos/pose_out.mp4", help="Path to save annotated video")
    ap.add_argument("--pose-ckpt", default="outputs/checkpoints/model2_pose/best.pt")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading Pose model on {device}...")
    pose_model = load_pose_model(Path(args.pose_ckpt), device)
    pose_tf = _build_pose_tf()
    print("✓ Model loaded successfully")

    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        print(f"Error: could not open video {args.input}")
        return

    # Setup VideoWriter
    fps_in = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    out_dir = Path(args.output).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(args.output, fourcc, fps_in, (width, height))

    print(f"Processing video: {args.input}")
    print(f"Saving to: {args.output}")

    frame_count = 0
    
    with torch.no_grad():
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            t_start = time.time()
            face_detected = False
            yaw, pitch, roll = None, None, None

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = _FACE_CASCADE.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
            face_detected = len(faces) > 0

            roi_bgr = detect_face_crop(frame)
            roi_rgb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB)
            pil_rgb = Image.fromarray(roi_rgb).convert("RGB")
            x_pose = pose_tf(pil_rgb).unsqueeze(0).to(device)
            pose_pred = pose_model(x_pose).squeeze(0).cpu().numpy()
            
            yaw, pitch, roll = float(pose_pred[0]), float(pose_pred[1]), float(pose_pred[2])

            # Calculate processing FPS
            t_end = time.time()
            fps = 1.0 / max(t_end - t_start, 1e-6)

            frame = draw_ui(frame, yaw, pitch, roll, face_detected, fps)
            
            out.write(frame)
            cv2.imshow("Model 2 - Pose Testing", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    out.release()
    cv2.destroyAllWindows()
    print(f"Done! Processed {frame_count} frames. Video saved to {args.output}")

if __name__ == "__main__":
    main()
