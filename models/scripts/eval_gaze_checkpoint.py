"""Evaluate one gaze checkpoint on the test set at its own stored img_size.

Usage (from models/, venvpy312):
    python scripts/eval_gaze_checkpoint.py outputs/checkpoints/model1_gaze/best.pt
    python scripts/eval_gaze_checkpoint.py outputs/checkpoints/model1_gaze/last.pt
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.model1_gaze.dataset import LABEL4, MPIIGaze4Class
from src.model1_gaze.model import build_model


def evaluate(ckpt_path: Path) -> dict:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    img_size = int(ckpt.get("img_size", 224))
    ds = MPIIGaze4Class(Path("data/processed/model1_gaze/test.csv"), img_size=img_size, train=False)
    loader = DataLoader(ds, batch_size=256, shuffle=False, num_workers=4, persistent_workers=True)

    model = build_model(num_classes=ckpt["num_classes"], pretrained=False).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    y_true, y_pred = [], []
    with torch.no_grad():
        for x, y in loader:
            logits = model(x.to(device))
            y_pred.append(torch.argmax(logits, dim=1).cpu().numpy())
            y_true.append(y.numpy())
    y_true = np.concatenate(y_true)
    y_pred = np.concatenate(y_pred)

    names = [k for k, _ in sorted(LABEL4.items(), key=lambda kv: kv[1])]
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, average="macro")
    print(f"\nCheckpoint : {ckpt_path}  (epoch {ckpt.get('epoch')}, img_size {img_size}, device {device})")
    print(f"Test       : {len(ds):,} samples")
    print(f"Accuracy   : {acc:.4f}   Macro-F1: {f1:.4f}")
    print(classification_report(y_true, y_pred, target_names=names, digits=4))
    print("Confusion (rows=true):")
    print(confusion_matrix(y_true, y_pred))
    return {"checkpoint": str(ckpt_path), "epoch": ckpt.get("epoch"), "img_size": img_size,
            "accuracy": float(acc), "macro_f1": float(f1)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: eval_gaze_checkpoint.py <checkpoint.pt> [more...]")
    for arg in sys.argv[1:]:
        evaluate(Path(arg))
