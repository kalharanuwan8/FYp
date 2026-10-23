"""
Test Model 1 (Gaze) on a pre-recorded video.
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
from torchvision.models import mobilenet_v2

# ─── Face / Eye detector (OpenCV Haar) ──────────────────────────────────────────
_FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_EYE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")

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

# ─── Drawing helpers ─────────────────────────────────────────────────────────
COLOR_GREEN = (0, 220, 80)
COLOR_RED = (0, 60, 255)
COLOR_YELLOW = (0, 220, 255)
COLOR_WHITE = (255, 255, 255)
COLOR_PANEL = (35, 35, 50)

def draw_bar(frame, label, val, x, y, w=180, h=12, color=COLOR_GREEN):
    cv2.rectangle(frame, (x, y), (x + w, y + h), (60, 60, 70), -1)
    cv2.rectangle(frame, (x, y), (x + int(w * val), y + h), color, -1)
    cv2.putText(frame, f"{label}: {val:.0%}", (x + w + 6, y + h),
                cv2.FONT_HERSHEY_SIMPLEX, 0.36, (180, 180, 180), 1, cv2.LINE_AA)

def draw_ui(frame, gaze_label, gaze_conf, face_detected, fps):
    h, w = frame.shape[:2]
    panel_w = 300
    panel_h = 160

    overlay = frame.copy()
    cv2.rectangle(overlay, (8, 8), (panel_w, panel_h), COLOR_PANEL, -1)
    cv2.addWeighted(overlay, 0.80, frame, 0.20, 0, frame)

    cv2.putText(frame, "MODEL 1: GAZE TRACKING", (18, 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_WHITE, 1, cv2.LINE_AA)
    cv2.line(frame, (18, 44), (panel_w - 10, 44), (80, 80, 100), 1)

    fd_color = COLOR_GREEN if face_detected else COLOR_RED
    cv2.putText(frame, f"Face: {'detected' if face_detected else 'NOT FOUND'}",
                (18, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.42, fd_color, 1, cv2.LINE_AA)

    g_col = COLOR_GREEN if gaze_label == "center" else COLOR_YELLOW
    cv2.putText(frame, f"Gaze: {gaze_label.upper() if gaze_label else 'N/A':<7}", (18, 96),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, g_col, 2, cv2.LINE_AA)
    if gaze_label:
        draw_bar(frame, "conf", gaze_conf, 18, 110, color=g_col)

    cv2.putText(frame, f"FPS: {fps:.0f}", (w - 100, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (140, 140, 180), 1, cv2.LINE_AA)
    return frame

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to input video file")
    ap.add_argument("--output", default="outputs/annotated_videos/gaze_out.mp4", help="Path to save annotated video")
    ap.add_argument("--gaze-ckpt", default="outputs/checkpoints/model1_gaze/best.pt")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading Gaze model on {device}...")
    gaze_model, gaze_img_size = load_gaze_model(Path(args.gaze_ckpt), device)
    gaze_tf = _build_gaze_tf(gaze_img_size)
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
    t0 = time.time()
    
    with torch.no_grad():
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            t_start = time.time()
            face_detected = False
            gaze_label = None
            gaze_conf = 0.0

            eye_crop, _ = detect_eye_crop(frame)
            if eye_crop is not None:
                face_detected = True
                img_gray = Image.fromarray(eye_crop).convert("L")
                x_gaze = gaze_tf(img_gray).unsqueeze(0).to(device)
                gaze_probs = torch.softmax(gaze_model(x_gaze), dim=1).squeeze(0).cpu().numpy()
                gaze_idx = int(gaze_probs.argmax())
                gaze_label = GAZE_LABELS[gaze_idx]
                gaze_conf = float(gaze_probs[gaze_idx])

            # Calculate processing FPS (not video FPS)
            t_end = time.time()
            fps = 1.0 / max(t_end - t_start, 1e-6)

            frame = draw_ui(frame, gaze_label, gaze_conf, face_detected, fps)
            
            out.write(frame)
            cv2.imshow("Model 1 - Gaze Testing", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    out.release()
    cv2.destroyAllWindows()
    print(f"Done! Processed {frame_count} frames. Video saved to {args.output}")

if __name__ == "__main__":
    main()
