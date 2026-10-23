from __future__ import annotations

import cv2
cv2.setNumThreads(0)

import csv
import math
import os
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from sklearn.metrics import f1_score, accuracy_score
from tqdm import tqdm

from src.model1_gaze.dataset import MPIIGaze4Class, GazeDataConfig, LABEL4
from src.model1_gaze.model import build_model


# -----------------------------
# Config
# -----------------------------
@dataclass(frozen=True)
class TrainConfig:
    data: GazeDataConfig = GazeDataConfig()

    epochs: int = 15
    batch_size: int = 128           # try 128 on RTX 4050 6GB; drop to 64 if OOM
    lr: float = 3e-4
    weight_decay: float = 1e-4

    # Windows-safe dataloader speed
    # num_workers=0 starves the GPU (~12 img/s on this dataset); 8 workers
    # with persistent_workers keeps up with AMP training. The __main__
    # freeze_support() guard below makes this safe on Windows.
    num_workers: int = 8
    prefetch_factor: int = 2
    persistent_workers: bool = True

    # Performance
    use_amp: bool = True
    grad_accum_steps: int = 1       # set to 2 or 4 if you need bigger effective batch

    # Output
    ckpt_dir: Path = Path("outputs/checkpoints/model1_gaze")
    log_dir: Path = Path("outputs/logs/model1_gaze")

    # Device
    device: str = "cuda" if torch.cuda.is_available() else "cpu"


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def compute_class_weights(train_csv: Path) -> torch.Tensor:
    """
    Inverse-frequency weights for CrossEntropyLoss.
    """
    import pandas as pd
    df = pd.read_csv(train_csv)
    df = df[df["label_name"].isin(LABEL4.keys())]
    counts = df["label_name"].value_counts()

    inv = []
    for name, idx in sorted(LABEL4.items(), key=lambda kv: kv[1]):
        c = float(counts.get(name, 1.0))
        inv.append(1.0 / c)

    inv = np.array(inv, dtype=np.float32)
    inv = inv / inv.sum() * len(inv)  # normalize avg weight ~1
    return torch.tensor(inv, dtype=torch.float32)


@torch.no_grad()
def run_eval(model: nn.Module, loader: DataLoader, device: str) -> Tuple[float, float]:
    model.eval()
    ys, preds = [], []

    for x, y in tqdm(loader, desc="Validating", leave=False):
        x = x.to(device, non_blocking=True)
        y = y.to(device, non_blocking=True)

        logits = model(x)
        p = torch.argmax(logits, dim=1)

        ys.append(y.detach().cpu().numpy())
        preds.append(p.detach().cpu().numpy())

    y_true = np.concatenate(ys)
    y_pred = np.concatenate(preds)

    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, average="macro")
    return acc, f1


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    opt: torch.optim.Optimizer,
    loss_fn: nn.Module,
    device: str,
    scaler: torch.cuda.amp.GradScaler | None,
    use_amp: bool,
    grad_accum_steps: int,
) -> float:
    model.train()
    losses = []

    t0 = time.time()
    n_seen = 0

    pbar = tqdm(loader, desc="Training", leave=False)
    opt.zero_grad(set_to_none=True)

    for step, (x, y) in enumerate(pbar, start=1):
        x = x.to(device, non_blocking=True)
        y = y.to(device, non_blocking=True)

        # forward
        if use_amp and scaler is not None:
            with torch.amp.autocast('cuda'):
                logits = model(x)
                loss = loss_fn(logits, y) / grad_accum_steps
            scaler.scale(loss).backward()
        else:
            logits = model(x)
            loss = loss_fn(logits, y) / grad_accum_steps
            loss.backward()

        # step
        if step % grad_accum_steps == 0:
            if use_amp and scaler is not None:
                scaler.step(opt)
                scaler.update()
            else:
                opt.step()
            opt.zero_grad(set_to_none=True)

        current_loss = float(loss.detach().item()) * grad_accum_steps
        losses.append(current_loss)

        n_seen += x.size(0)
        elapsed = max(1e-6, time.time() - t0)
        ips = n_seen / elapsed  # images per second

        pbar.set_postfix({
            "loss": f"{current_loss:.4f}",
            "avg": f"{np.mean(losses):.4f}",
            "img/s": f"{ips:.0f}",
        })

    return float(np.mean(losses)) if losses else math.nan


def run():
    cfg = TrainConfig()
    # Optional overrides (used for the stride-sampled retrain; defaults
    # preserve the original behaviour):
    #   GAZE_TRAIN_CSV=data/processed/model1_gaze/train_stride4.csv
    #   GAZE_EPOCHS=15
    if os.environ.get("GAZE_TRAIN_CSV"):
        cfg = replace(cfg, data=replace(cfg.data, train_csv=Path(os.environ["GAZE_TRAIN_CSV"])))
    if os.environ.get("GAZE_EPOCHS"):
        cfg = replace(cfg, epochs=int(os.environ["GAZE_EPOCHS"]))

    ensure_dir(cfg.ckpt_dir)
    ensure_dir(cfg.log_dir)

    # Speed knobs
    if torch.cuda.is_available():
        torch.backends.cudnn.benchmark = True

    train_ds = MPIIGaze4Class(cfg.data.train_csv, img_size=cfg.data.img_size, train=True)
    val_ds = MPIIGaze4Class(cfg.data.val_csv, img_size=cfg.data.img_size, train=False)

    pin = torch.cuda.is_available()

    # NOTE: persistent_workers requires num_workers > 0
    persistent = cfg.persistent_workers and cfg.num_workers > 0

    train_loader = DataLoader(
        train_ds,
        batch_size=cfg.batch_size,
        shuffle=True,
        num_workers=cfg.num_workers,
        pin_memory=pin,
        persistent_workers=persistent,
        prefetch_factor=cfg.prefetch_factor if cfg.num_workers > 0 else None,
        drop_last=False,
    )

    val_loader = DataLoader(
        val_ds,
        batch_size=cfg.batch_size,
        shuffle=False,
        num_workers=cfg.num_workers,
        pin_memory=pin,
        persistent_workers=persistent,
        prefetch_factor=cfg.prefetch_factor if cfg.num_workers > 0 else None,
        drop_last=False,
    )

    model = build_model(num_classes=cfg.data.num_classes, pretrained=True).to(cfg.device)

    class_w = compute_class_weights(cfg.data.train_csv).to(cfg.device)
    loss_fn = nn.CrossEntropyLoss(weight=class_w)

    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=cfg.epochs, eta_min=cfg.lr / 20)
    scaler = torch.amp.GradScaler('cuda', enabled=(cfg.use_amp and torch.cuda.is_available()))

    log_path = cfg.log_dir / "train_log.csv"
    best_path = cfg.ckpt_dir / "best.pt"
    last_path = cfg.ckpt_dir / "last.pt"

    # ── Resume from last.pt if it exists ──────────────────────────────────────
    start_epoch = 1
    best_f1 = -1.0

    if last_path.exists():
        print(f"\n>>  Resuming from: {last_path}")
        ckpt = torch.load(last_path, map_location=cfg.device, weights_only=False)
        model.load_state_dict(ckpt["model_state"])
        start_epoch = int(ckpt.get("epoch", 0)) + 1

        if "optimizer_state" in ckpt:
            opt.load_state_dict(ckpt["optimizer_state"])
        if "scheduler_state" in ckpt:
            scheduler.load_state_dict(ckpt["scheduler_state"])
        if "scaler_state" in ckpt:
            scaler.load_state_dict(ckpt["scaler_state"])
        if "best_f1" in ckpt:
            best_f1 = float(ckpt["best_f1"])
        # Older last.pt files stored best_f1 before that epoch's update
        # (so it can be -1 on resume). Recover it from the log if needed,
        # otherwise a worse resumed epoch would overwrite best.pt.
        if best_f1 < 0 and log_path.exists():
            import pandas as _pd
            # Old logs have a 4-column header but 5 fields per row (lr was
            # appended without a header column), so name columns explicitly.
            _log = _pd.read_csv(
                log_path, header=0,
                names=["epoch", "train_loss", "val_acc", "val_f1", "lr"],
            )
            if len(_log):
                best_f1 = float(_log["val_f1"].max())

        print(f"    Continuing at epoch {start_epoch}/{cfg.epochs} | best F1 so far: {best_f1:.4f}\n")
    else:
        # Fresh run — write log header
        with open(log_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["epoch", "train_loss", "val_acc", "val_f1", "lr"])  # header matches rows below

    print(f"Device: {cfg.device}")
    print(f"AMP: {cfg.use_amp and torch.cuda.is_available()}")
    print(f"Batch size: {cfg.batch_size} | Grad accum: {cfg.grad_accum_steps} "
          f"(effective batch={cfg.batch_size * cfg.grad_accum_steps})")
    print(f"Workers: {cfg.num_workers} | pin_memory: {pin} | persistent_workers: {persistent}")
    print(f"Train samples: {len(train_ds):,} | Val samples: {len(val_ds):,}")
    print(f"Saving best checkpoint to: {best_path}")
    print("Class weights:", class_w.detach().cpu().numpy())

    for epoch in range(start_epoch, cfg.epochs + 1):
        train_loss = train_one_epoch(
            model=model,
            loader=train_loader,
            opt=opt,
            loss_fn=loss_fn,
            device=cfg.device,
            scaler=scaler,
            use_amp=(cfg.use_amp and torch.cuda.is_available()),
            grad_accum_steps=max(1, cfg.grad_accum_steps),
        )
        val_acc, val_f1 = run_eval(model, val_loader, cfg.device)
        scheduler.step()
        current_lr = scheduler.get_last_lr()[0]

        print(f"[{epoch:02d}/{cfg.epochs}] loss={train_loss:.4f} val_acc={val_acc:.4f} val_f1={val_f1:.4f} lr={current_lr:.2e}")

        with open(log_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([epoch, f"{train_loss:.6f}", f"{val_acc:.6f}", f"{val_f1:.6f}", f"{current_lr:.6e}"])

        is_best = val_f1 > best_f1
        if is_best:
            best_f1 = val_f1

        # Always save full state for resuming (with the updated best_f1)
        torch.save({
            "model_state": model.state_dict(),
            "optimizer_state": opt.state_dict(),
            "scheduler_state": scheduler.state_dict(),
            "scaler_state": scaler.state_dict(),
            "num_classes": cfg.data.num_classes,
            "label_map": LABEL4,
            "img_size": cfg.data.img_size,
            "epoch": epoch,
            "best_f1": best_f1,
        }, last_path)

        if is_best:
            torch.save({
                "model_state": model.state_dict(),
                "num_classes": cfg.data.num_classes,
                "label_map": LABEL4,
                "img_size": cfg.data.img_size,
                "epoch": epoch,
            }, best_path)
            print(f"  [OK] New best val F1={best_f1:.4f} -> saved best.pt")

    print(f"\nDone. Best val macro-F1: {best_f1:.4f}")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    # Required on Windows when num_workers>0
    # (especially if dataset uses PIL / transforms)
    torch.multiprocessing.freeze_support()
    run()
