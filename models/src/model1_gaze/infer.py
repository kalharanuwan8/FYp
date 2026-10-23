from pathlib import Path
import torch
import cv2
import numpy as np
import pandas as pd
from PIL import Image
from torchvision import transforms as T

from src.model1_gaze.model import build_model
from src.model1_gaze.dataset import LABEL4


def build_tf(img_size: int = 224):
    return T.Compose([
        T.Resize((img_size, img_size)),
        T.ToTensor(),
        T.Lambda(lambda x: x.repeat(3, 1, 1) if x.shape[0] == 1 else x),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])


@torch.no_grad()
def load_model(ckpt_path: Path, device: str):
    ckpt = torch.load(ckpt_path, map_location=device)
    model = build_model(num_classes=ckpt["num_classes"], pretrained=False).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    return model, ckpt


@torch.no_grad()
def infer_video(video_path: Path, ckpt_path: Path, out_csv: Path, window_sec: float = 2.0, stride_sec: float = 1.0, append: bool = False):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, ckpt = load_model(ckpt_path, device)
    img_size = ckpt.get("img_size", 224)
    tf = build_tf(img_size)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0  # Fallback

    win_frames = int(window_sec * fps)
    stride_frames = int(stride_sec * fps)

    frame_idx = 0
    all_probs = []
    timestamps = []

    print(f"Processing video: {video_path} ({fps} FPS)")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Convert BGR (OpenCV) to RGB for transforms, then grayscale for model if needed
        # The current tf expects 3-channel (repeated) if grayscale is provided
        # Mapping to PIL image to follow the original infer_image logic
        img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("L")
        x = tf(img_pil).unsqueeze(0).to(device)
        
        logits = model(x)
        probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()
        
        all_probs.append(probs)
        timestamps.append(frame_idx / fps)
        frame_idx += 1
        
        if frame_idx % 100 == 0:
            print(f"Processed {frame_idx} frames...")

    cap.release()

    # Windowing aggregation
    results = []
    inv_label = {v: k for k, v in LABEL4.items()}
    # Prefix probability columns with "p_" for fusion/prepare.py
    prob_cols = [f"p_{inv_label[i]}" for i in range(len(LABEL4))]
    columns = ["video_id", "window_start_sec", "pred_name", "confidence"] + prob_cols

    video_id = video_path.stem

    # Sliding window
    for start_idx in range(0, len(all_probs) - win_frames + 1, stride_frames):
        end_idx = start_idx + win_frames
        window_probs = np.mean(all_probs[start_idx:end_idx], axis=0)
        
        pred_idx = int(window_probs.argmax())
        pred_name = inv_label[pred_idx]
        conf = float(window_probs[pred_idx])
        ts = timestamps[start_idx]
        
        row = [video_id, ts, pred_name, conf] + window_probs.tolist()
        results.append(row)

    df = pd.DataFrame(results, columns=columns)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    
    # Handle append
    write_header = not out_csv.exists() or not append
    write_mode = "a" if append else "w"
    df.to_csv(out_csv, index=False, mode=write_mode, header=write_header)
    
    print(f"Saved window predictions to {out_csv} (append={append})")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    # Support both modes
    ap.add_argument("--img", type=str, help="Path to image for single inference")
    ap.add_argument("--video", type=str, help="Path to video for windowed inference")
    ap.add_argument("--out", type=str, default="data/processed/model1_gaze/window_preds.csv", help="Output CSV path")
    ap.add_argument("--ckpt", default="outputs/checkpoints/model1_gaze/best.pt", type=str)
    ap.add_argument("--win", type=float, default=2.0, help="Window size in seconds")
    ap.add_argument("--stride", type=float, default=1.0, help="Stride in seconds")
    ap.add_argument("--append", action="store_true", help="Append results to existing CSV")
    args = ap.parse_args()

    if args.img:
        pred, conf, probs = infer_image(Path(args.img), Path(args.ckpt))
        print(f"Pred: {pred}  conf={conf:.3f}")
        print("Probs:", probs)
    elif args.video:
        infer_video(
            Path(args.video), 
            Path(args.ckpt), 
            Path(args.out), 
            window_sec=args.win, 
            stride_sec=args.stride,
            append=args.append
        )
    else:
        ap.print_help()
