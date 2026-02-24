# model2_pose Training loop
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
from PIL import Image

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import models
from torchvision import transforms
from tqdm import tqdm


# -------------------------
# Dataset
# -------------------------
class PoseDataset(Dataset):
    def __init__(self, csv_path: Path, img_size: int = 224):
        self.df = pd.read_csv(csv_path)
        self.img_size = img_size

        self.tf = transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx: int):
        row = self.df.iloc[idx]
        img_path = row["img_path"]

        img = Image.open(img_path).convert("RGB")
        x = self.tf(img)

        # regression targets in degrees
        y = torch.tensor([row["yaw_deg"], row["pitch_deg"], row["roll_deg"]], dtype=torch.float32)
        return x, y


# -------------------------
# Model
# -------------------------
class PoseRegressor(nn.Module):
    def __init__(self):
        super().__init__()
        base = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
        # replace final layer with 3 outputs
        in_features = base.fc.in_features
        base.fc = nn.Linear(in_features, 3)
        self.net = base

    def forward(self, x):
        return self.net(x)


# -------------------------
# Train / Eval
# -------------------------
@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    total_loss = 0.0
    total_mae = torch.zeros(3, device=device)

    crit = nn.SmoothL1Loss()

    n = 0
    for x, y in loader:
        x = x.to(device, non_blocking=True)
        y = y.to(device, non_blocking=True)

        pred = model(x)
        loss = crit(pred, y)

        total_loss += loss.item() * x.size(0)
        total_mae += (pred - y).abs().sum(dim=0)
        n += x.size(0)

    avg_loss = total_loss / max(1, n)
    avg_mae = (total_mae / max(1, n)).detach().cpu().numpy()  # yaw, pitch, roll MAE in degrees
    return avg_loss, avg_mae


def save_ckpt(path: Path, model, optimizer, scaler, epoch: int, best_val: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "epoch": epoch,
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "scaler": scaler.state_dict() if scaler is not None else None,
        "best_val": best_val,
    }, path)


def load_ckpt(path: Path, model, optimizer=None, scaler=None):
    ckpt = torch.load(path, map_location="cpu")
    model.load_state_dict(ckpt["model"])
    if optimizer is not None and "optimizer" in ckpt and ckpt["optimizer"] is not None:
        optimizer.load_state_dict(ckpt["optimizer"])
    if scaler is not None and "scaler" in ckpt and ckpt["scaler"] is not None:
        scaler.load_state_dict(ckpt["scaler"])
    start_epoch = int(ckpt.get("epoch", 0)) + 1
    best_val = float(ckpt.get("best_val", 1e9))
    return start_epoch, best_val


def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    data_root = Path(args.data_root)
    train_csv = data_root / "train.csv"
    val_csv = data_root / "val.csv"

    train_ds = PoseDataset(train_csv, img_size=args.img_size)
    val_ds = PoseDataset(val_csv, img_size=args.img_size)

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=True,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=True,
    )

    print(f"Train samples: {len(train_ds):,} | Val samples: {len(val_ds):,}")

    model = PoseRegressor().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.wd)
    crit = nn.SmoothL1Loss()

    use_amp = args.amp and device.type == "cuda"
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

    out_dir = Path(args.out_dir)
    ckpt_dir = out_dir / "checkpoints" / "model2_pose"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    start_epoch = 0
    best_val = 1e9

    if args.resume:
        resume_path = Path(args.resume)
        print(f"Resuming from: {resume_path}")
        start_epoch, best_val = load_ckpt(resume_path, model, optimizer, scaler)
        print(f"Resume epoch: {start_epoch} | best_val: {best_val:.6f}")

    # training loop
    for epoch in range(start_epoch, args.epochs):
        model.train()
        running = 0.0
        n = 0

        pbar = tqdm(train_loader, desc=f"Epoch {epoch+1}/{args.epochs}", leave=True)
        for x, y in pbar:
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)

            optimizer.zero_grad(set_to_none=True)

            with torch.cuda.amp.autocast(enabled=use_amp):
                pred = model(x)
                loss = crit(pred, y)

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            running += loss.item() * x.size(0)
            n += x.size(0)
            avg = running / max(1, n)

            pbar.set_postfix(loss=f"{loss.item():.4f}", avg=f"{avg:.4f}")

        train_loss = running / max(1, n)
        val_loss, val_mae = evaluate(model, val_loader, device)

        print("\n" + "-" * 60)
        print(f"Epoch {epoch+1}: train_loss={train_loss:.6f} | val_loss={val_loss:.6f}")
        print(f"Val MAE (deg): yaw={val_mae[0]:.2f}, pitch={val_mae[1]:.2f}, roll={val_mae[2]:.2f}")
        print("-" * 60)

        # save last
        save_ckpt(ckpt_dir / "last.pt", model, optimizer, scaler, epoch, best_val)

        # save best
        if val_loss < best_val:
            best_val = val_loss
            print(f"✅ New best val_loss={best_val:.6f} -> saving best.pt")
            save_ckpt(ckpt_dir / "best.pt", model, optimizer, scaler, epoch, best_val)

    print("\nDone.")
    print(f"Best val loss: {best_val:.6f}")
    print(f"Best checkpoint: {ckpt_dir / 'best.pt'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=str, default="data/processed/model2_pose",
                    help="Folder containing train.csv/val.csv/test.csv")
    ap.add_argument("--out-dir", type=str, default="outputs",
                    help="Output folder for checkpoints/logs")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--wd", type=float, default=1e-4)
    ap.add_argument("--num-workers", type=int, default=4)
    ap.add_argument("--amp", action="store_true", help="Enable mixed precision (CUDA only)")
    ap.add_argument("--resume", type=str, default="", help="Path to checkpoint to resume from")
    args = ap.parse_args()

    train(args)


if __name__ == "__main__":
    main()
