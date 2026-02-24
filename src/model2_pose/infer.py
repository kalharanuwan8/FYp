# model2_pose Inference script
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms, models


def build_model() -> nn.Module:
    m = models.resnet18(weights=None)
    m.fc = nn.Linear(m.fc.in_features, 3)  # yaw, pitch, roll
    return m


def build_tf(img_size: int = 224):
    return transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


def crop_center_bgr(img_bgr: np.ndarray, frac: float = 0.60) -> np.ndarray:
    """
    Simple fallback crop (center region). Not perfect face crop,
    but works for demonstration/inference without extra detectors.
    """
    h, w = img_bgr.shape[:2]
    cw, ch = int(w * frac), int(h * frac)
    x1 = max(0, (w - cw) // 2)
    y1 = max(0, (h - ch) // 2)
    return img_bgr[y1:y1 + ch, x1:x1 + cw]


@torch.no_grad()
def infer_image(
    img_path: Path,
    ckpt_path: Path,
    img_size: int = 224,
    crop_frac: float = 0.60,
) -> tuple[float, float, float]:
    device = "cuda" if torch.cuda.is_available() else "cpu"

    ckpt = torch.load(ckpt_path, map_location=device)

    model = build_model().to(device)
    state_dict = {k.replace("net.", ""): v for k, v in ckpt["model"].items()}
    model.load_state_dict(state_dict)
    model.eval()

    tf = build_tf(img_size)

    # Read with OpenCV for easy crop; convert to RGB PIL
    img_bgr = cv2.imread(str(img_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Could not read image: {img_path}")

    roi_bgr = crop_center_bgr(img_bgr, frac=crop_frac)
    roi_rgb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(roi_rgb).convert("RGB")

    x = tf(pil).unsqueeze(0).to(device)
    pred = model(x).squeeze(0).cpu().numpy()

    yaw, pitch, roll = float(pred[0]), float(pred[1]), float(pred[2])
    return yaw, pitch, roll


@torch.no_grad()
def infer_video(
    video_path: Path,
    ckpt_path: Path,
    out_csv: Path,
    img_size: int = 224,
    crop_frac: float = 0.60,
    window_sec: float = 2.0,
    stride_sec: float = 1.0,
    append: bool = False,
):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    ckpt = torch.load(ckpt_path, map_location=device)

    model = build_model().to(device)
    state_dict = {k.replace("net.", ""): v for k, v in ckpt["model"].items()}
    model.load_state_dict(state_dict)
    model.eval()

    tf = build_tf(img_size)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    win_frames = int(window_sec * fps)
    stride_frames = int(stride_sec * fps)

    frame_idx = 0
    all_preds = []
    timestamps = []

    print(f"Processing video: {video_path} ({fps} FPS)")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        roi_bgr = crop_center_bgr(frame, frac=crop_frac)
        roi_rgb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(roi_rgb).convert("RGB")

        x = tf(pil).unsqueeze(0).to(device)
        pred = model(x).squeeze(0).cpu().numpy()

        all_preds.append(pred)
        timestamps.append(frame_idx / fps)
        frame_idx += 1

        if frame_idx % 100 == 0:
            print(f"Processed {frame_idx} frames...")

    cap.release()

    if not all_preds:
        print("No frames processed.")
        return

    # Windowing aggregation
    results = []
    columns = ["video_id", "window_start_sec", "yaw_mean", "pitch_mean", "roll_mean"]
    video_id = video_path.stem

    # Sliding window
    for start_idx in range(0, len(all_preds) - win_frames + 1, stride_frames):
        end_idx = start_idx + win_frames
        window_preds = np.mean(all_preds[start_idx:end_idx], axis=0)
        
        ts = timestamps[start_idx]
        row = [video_id, ts] + window_preds.tolist()
        results.append(row)

    df = pd.DataFrame(results, columns=columns)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    
    # Handle append
    write_header = not out_csv.exists() or not append
    write_mode = "a" if append else "w"
    df.to_csv(out_csv, index=False, mode=write_mode, header=write_header)
    
    print(f"Saved window predictions to {out_csv} (append={append})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", type=str, help="Path to an image frame")
    ap.add_argument("--video", type=str, help="Path to video for windowed inference")
    ap.add_argument("--out", type=str, default="data/processed/model2_pose/window_pose.csv", help="Output CSV path")
    ap.add_argument("--ckpt", default="outputs/checkpoints/model2_pose/best.pt", type=str)
    ap.add_argument("--img-size", default=224, type=int)
    ap.add_argument("--crop-frac", default=0.60, type=float)
    ap.add_argument("--win", type=float, default=2.0, help="Window size in seconds")
    ap.add_argument("--stride", type=float, default=1.0, help="Stride in seconds")
    ap.add_argument("--append", action="store_true", help="Append results to existing CSV")
    args = ap.parse_args()

    if args.img:
        yaw, pitch, roll = infer_image(
            Path(args.img),
            Path(args.ckpt),
            img_size=args.img_size,
            crop_frac=args.crop_frac,
        )
        print(f"Yaw (deg):   {yaw:.2f}")
        print(f"Pitch (deg): {pitch:.2f}")
        print(f"Roll (deg):  {roll:.2f}")
    elif args.video:
        infer_video(
            Path(args.video),
            Path(args.ckpt),
            Path(args.out),
            img_size=args.img_size,
            crop_frac=args.crop_frac,
            window_sec=args.win,
            stride_sec=args.stride,
            append=args.append,
        )
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
