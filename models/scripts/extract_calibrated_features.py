import cv2
import time
import torch
import joblib
import subprocess
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from PIL import Image
from torchvision import transforms as T
from torchvision import models
from torchvision.models import mobilenet_v2
import torch.nn as nn

# --- Model Building Helpers ---
def _build_gaze_model(num_classes=4):
    m = mobilenet_v2(weights=None)
    m.classifier[1] = nn.Linear(m.classifier[1].in_features, num_classes)
    return m

def _build_gaze_tf(img_size=224):
    return T.Compose([
        T.Resize((img_size, img_size)),
        T.ToTensor(),
        T.Lambda(lambda x: x.repeat(3, 1, 1) if x.shape[0] == 1 else x),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

def _build_pose_model():
    m = models.resnet18(weights=None)
    m.fc = nn.Linear(m.fc.in_features, 3)
    return m

def _build_pose_tf(img_size=224):
    return T.Compose([
        T.Resize((img_size, img_size)),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

def detect_eye_crop(frame, cascade_path="outputs/checkpoints/haarcascade_frontalface_default.xml"):
    try:
        if not Path(cascade_path).exists(): return None
        face_cascade = cv2.CascadeClassifier(cascade_path)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        if len(faces) == 0: return None
        fx, fy, fw, fh = max(faces, key=lambda b: b[2] * b[3])
        ey_top, ey_bot = fy + int(0.18 * fh), fy + int(0.55 * fh)
        ex_left, ex_right = fx + int(0.10 * fw), fx + int(0.90 * fw)
        return frame[ey_top:ey_bot, ex_left:ex_right]
    except Exception:
        return None

def process_video_calibrated(video_path: Path, video_id: str, gaze_model, pose_model, device: str, calib_sec: float = 1.0, window_sec: float = 2.0, stride_sec: float = 1.0):
    print(f"\n=======================================================")
    print(f"Processing {video_id} ({video_path.name}) with calib_sec={calib_sec}s...")
    print(f"=======================================================", flush=True)
    
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {video_path}")
        
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    win_frames = int(window_sec * fps)
    stride_frames = int(stride_sec * fps)
    
    gaze_tf = _build_gaze_tf(224)
    pose_tf = _build_pose_tf(224)
    
    calib_frames_total = max(1, int(fps * calib_sec)) if calib_sec > 0 else 0
    calibrating = calib_frames_total
    accum_gaze = np.zeros(4, dtype=np.float32)
    accum_pose = np.zeros(3, dtype=np.float32)
    base_gaze = np.zeros(4, dtype=np.float32)
    base_pose = np.zeros(3, dtype=np.float32)
    is_calibrated = False
    
    all_gaze_probs = []
    all_pose_angles = []
    timestamps = []
    
    frame_idx = 0
    t0 = time.time()
    
    with torch.no_grad():
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            # Gaze input
            eye_crop = detect_eye_crop(frame)
            if eye_crop is not None:
                img_gaze = Image.fromarray(eye_crop).convert("L")
            else:
                img_gaze = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("L")
            x_gaze = gaze_tf(img_gaze).unsqueeze(0).to(device)
            raw_gaze_logits = gaze_model(x_gaze).squeeze(0).cpu().numpy()
            
            # Pose input
            h, w = frame.shape[:2]
            crop_frac = 0.60
            ch, cw = int(h * crop_frac), int(w * crop_frac)
            sy, sx = (h - ch) // 2, (w - cw) // 2
            roi_bgr = frame[sy:sy+ch, sx:sx+cw]
            roi_rgb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB)
            img_pose = Image.fromarray(roi_rgb).convert("RGB")
            x_pose = pose_tf(img_pose).unsqueeze(0).to(device)
            raw_pose = pose_model(x_pose).squeeze(0).cpu().numpy()
            
            # Calibration logic
            if calibrating > 0:
                accum_gaze += raw_gaze_logits
                accum_pose += raw_pose
                calibrating -= 1
                if calibrating == 0:
                    base_gaze = accum_gaze / calib_frames_total
                    base_pose = accum_pose / calib_frames_total
                    is_calibrated = True
            
            adj_gaze = raw_gaze_logits - base_gaze
            if is_calibrated:
                adj_gaze[0] += 2.0  # Boost center logit after calibration
                
            exp_logits = np.exp(adj_gaze - np.max(adj_gaze))
            gaze_probs = exp_logits / exp_logits.sum()
            
            adj_pose = raw_pose - base_pose
            
            all_gaze_probs.append(gaze_probs)
            all_pose_angles.append(adj_pose)
            timestamps.append(frame_idx / fps)
            
            frame_idx += 1
            if frame_idx % 500 == 0:
                print(f"  Processed {frame_idx} frames... ({frame_idx/(time.time()-t0):.1f} fps)", flush=True)
                
    cap.release()
    print(f"--> Finished {frame_idx} frames in {time.time()-t0:.1f}s!", flush=True)
    
    # Aggregation into windows
    gaze_rows = []
    pose_rows = []
    inv_label = {0: "center", 1: "left", 2: "right", 3: "down"}
    
    for start_idx in range(0, len(all_gaze_probs) - win_frames + 1, stride_frames):
        end_idx = start_idx + win_frames
        win_g = np.mean(all_gaze_probs[start_idx:end_idx], axis=0)
        win_p = np.mean(all_pose_angles[start_idx:end_idx], axis=0)
        ts = timestamps[start_idx]
        
        pred_idx = int(win_g.argmax())
        pred_name = inv_label[pred_idx]
        conf = float(win_g[pred_idx])
        
        gaze_rows.append([video_id, ts, pred_name, conf, float(win_g[0]), float(win_g[1]), float(win_g[2]), float(win_g[3])])
        pose_rows.append([video_id, ts, float(win_p[0]), float(win_p[1]), float(win_p[2])])
        
    gaze_df = pd.DataFrame(gaze_rows, columns=["video_id", "window_start_sec", "pred_name", "confidence", "p_center", "p_left", "p_right", "p_down"])
    pose_df = pd.DataFrame(pose_rows, columns=["video_id", "window_start_sec", "yaw_mean", "pitch_mean", "roll_mean"])
    
    out_gaze = Path(f"data/processed/model1_gaze/window_preds_{video_id}.csv")
    out_pose = Path(f"data/processed/model2_pose/window_pose_{video_id}.csv")
    out_gaze.parent.mkdir(parents=True, exist_ok=True)
    out_pose.parent.mkdir(parents=True, exist_ok=True)
    
    gaze_df.to_csv(out_gaze, index=False)
    pose_df.to_csv(out_pose, index=False)
    print(f"Saved {len(gaze_df)} windows to {out_gaze} and {out_pose}!", flush=True)

def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}", flush=True)
    
    # Load checkpoints
    gaze_ckpt = torch.load("outputs/checkpoints/model1_gaze/best.pt", map_location=device, weights_only=False)
    gaze_model = _build_gaze_model(num_classes=gaze_ckpt["num_classes"]).to(device)
    gaze_model.load_state_dict(gaze_ckpt["model_state"])
    gaze_model.eval()
    
    pose_ckpt = torch.load("outputs/checkpoints/model2_pose/best.pt", map_location=device, weights_only=False)
    pose_model = _build_pose_model().to(device)
    pose_model.load_state_dict({k.replace("net.", ""): v for k, v in pose_ckpt["model"].items()})
    pose_model.eval()
    
    raw_dir = Path("D:/uni/6th sem/IRP/Data collection/raw data/participant 1")
    videos = [
        ("distracted", raw_dir / "distracted.mp4"),
        ("forced", raw_dir / "focused.mp4"),
        ("natural", raw_dir / "natural.mp4")
    ]
    
    t_start = time.time()
    for vid_id, vid_path in videos:
        process_video_calibrated(vid_path, vid_id, gaze_model, pose_model, device, calib_sec=1.0, window_sec=2.0, stride_sec=1.0)
        
    print(f"\nAll videos processed in {(time.time()-t_start)/60:.2f} minutes!", flush=True)
    
    # Run dataset prep and training
    py = sys.executable
    print("\nRunning Model 5 prep.py...", flush=True)
    subprocess.run([py, "-u", "-m", "src.model5_fusion.prep"], check=True)
    
    print("\nRe-training Model 5 Fusion...", flush=True)
    subprocess.run([py, "-u", "-m", "src.model5_fusion.train"], check=True)
    print("\n=======================================================")
    print("[SUCCESS] Calibrated feature extraction and Model 5 training complete!")
    print("=======================================================", flush=True)

if __name__ == "__main__":
    main()
