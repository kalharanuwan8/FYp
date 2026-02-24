# model1_gaze Evaluation loop
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt

from src.model1_gaze.dataset import MPIIGaze4Class, GazeDataConfig, LABEL4
from src.model1_gaze.model import build_model


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


@torch.no_grad()
def main():
    data = GazeDataConfig()
    ckpt_path = Path("outputs/checkpoints/model1_gaze/best.pt")
    assert ckpt_path.exists(), f"Missing checkpoint: {ckpt_path}"

    device = "cuda" if torch.cuda.is_available() else "cpu"
    test_ds = MPIIGaze4Class(data.test_csv, img_size=data.img_size, train=False)
    test_loader = DataLoader(test_ds, batch_size=512, shuffle=False, num_workers=4)

    model = build_model(num_classes=data.num_classes, pretrained=False).to(device)
    ckpt = torch.load(ckpt_path, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    y_true, y_pred = [], []
    for x, y in test_loader:
        x = x.to(device)
        logits = model(x)
        p = torch.argmax(logits, dim=1).cpu().numpy()
        y_pred.append(p)
        y_true.append(y.numpy())

    y_true = np.concatenate(y_true)
    y_pred = np.concatenate(y_pred)

    inv = {v: k for k, v in LABEL4.items()}
    target_names = [inv[i] for i in range(len(inv))]

    print("\nClassification report:")
    print(classification_report(y_true, y_pred, target_names=target_names, digits=4))

    cm = confusion_matrix(y_true, y_pred)
    print("\nConfusion matrix:\n", cm)

    out_dir = Path("outputs/reports/model1_gaze")
    ensure_dir(out_dir)

    # Plot confusion matrix
    fig = plt.figure()
    ax = fig.add_subplot(111)
    im = ax.imshow(cm)
    ax.set_title("Model 1 - Confusion Matrix (4-class)")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_xticks(range(len(target_names)))
    ax.set_yticks(range(len(target_names)))
    ax.set_xticklabels(target_names, rotation=30, ha="right")
    ax.set_yticklabels(target_names)

    # annotate
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center")

    fig.tight_layout()
    out_path = out_dir / "confusion_matrix.png"
    fig.savefig(out_path, dpi=200)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
