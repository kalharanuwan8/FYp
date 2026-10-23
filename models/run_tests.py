"""
run_tests.py — Individual model evaluation on held-out test sets.

Tests all trained models and prints a full report with metrics.
Results (confusion matrices, plots) are saved to outputs/reports/.

Usage:
    python run_tests.py               # test all models
    python run_tests.py --model gaze  # test one model (gaze|pose|engagement|fusion)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

# ─── helpers ─────────────────────────────────────────────────────────────────

PASS = "✅"
FAIL = "❌"
SKIP = "⚪"

def sep(title: str = ""):
    w = 60
    if title:
        print(f"\n{'─' * 4} {title} {'─' * max(0, w - len(title) - 6)}")
    else:
        print("─" * w)

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


# ─── Model 1 · Gaze ──────────────────────────────────────────────────────────

def test_model1_gaze():
    sep("Model 1 · Gaze Direction (MobileNetV2)")

    ckpt_path = Path("outputs/checkpoints/model1_gaze/best.pt")
    test_csv  = Path("data/processed/model1_gaze/test.csv")

    if not ckpt_path.exists():
        print(f"  {SKIP} Checkpoint not found: {ckpt_path}")
        return
    if not test_csv.exists():
        print(f"  {SKIP} Test CSV not found: {test_csv}")
        return

    import torch
    from torch.utils.data import DataLoader
    from sklearn.metrics import (
        classification_report, confusion_matrix,
        accuracy_score, f1_score
    )
    from src.model1_gaze.dataset import MPIIGaze4Class, GazeDataConfig, LABEL4
    from src.model1_gaze.model import build_model

    data   = GazeDataConfig()
    device = "cpu"   # CPU-only: avoids CUDA init conflicts, lighter on resources

    ckpt  = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    # Evaluate at the checkpoint's own training resolution, not the
    # config default (they differ after the 96px retrain).
    test_ds     = MPIIGaze4Class(test_csv, img_size=int(ckpt.get("img_size", data.img_size)), train=False)
    test_loader = DataLoader(test_ds, batch_size=256, shuffle=False,
                             num_workers=0, pin_memory=False)

    model = build_model(num_classes=ckpt["num_classes"], pretrained=False)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    epoch_trained = ckpt.get("epoch", "?")
    print(f"  Checkpoint epoch : {epoch_trained}")
    print(f"  Test samples     : {len(test_ds):,}")
    print("  Running on CPU (no CUDA)... ", end="", flush=True)

    y_true, y_pred = [], []
    with torch.no_grad():
        for i, (x, y) in enumerate(test_loader):
            logits = model(x)
            p = torch.argmax(logits, dim=1).numpy()
            y_pred.append(p)
            y_true.append(y.numpy())
            if (i + 1) % 5 == 0:
                print(".", end="", flush=True)
    print(" done")

    y_true = np.concatenate(y_true)
    y_pred = np.concatenate(y_pred)

    inv   = {v: k for k, v in LABEL4.items()}
    names = [inv[i] for i in range(len(inv))]

    acc = accuracy_score(y_true, y_pred)
    f1  = f1_score(y_true, y_pred, average="macro")

    print(f"\n  Test Accuracy  : {acc:.4f}  ({acc*100:.1f}%)")
    print(f"  Macro F1 Score : {f1:.4f}")
    print()
    print(classification_report(y_true, y_pred, target_names=names, digits=4))

    cm = confusion_matrix(y_true, y_pred)
    print("  Confusion Matrix (rows=True, cols=Pred):")
    print("          " + "  ".join(f"{n:>7}" for n in names))
    for i, row in enumerate(cm):
        print(f"  {names[i]:>7}   " + "  ".join(f"{v:>7}" for v in row))

    # Save confusion matrix plot
    try:
        import matplotlib
        matplotlib.use("Agg")   # non-interactive backend — no window popup
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 5))
        im = ax.imshow(cm, cmap="Blues")
        ax.set_title(f"Model 1 · Gaze — Confusion Matrix (epoch {epoch_trained})")
        ax.set_xlabel("Predicted"); ax.set_ylabel("True")
        ax.set_xticks(range(len(names))); ax.set_yticks(range(len(names)))
        ax.set_xticklabels(names, rotation=30, ha="right")
        ax.set_yticklabels(names)
        plt.colorbar(im, ax=ax)
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                        color="white" if cm[i, j] > cm.max() / 2 else "black")
        fig.tight_layout()
        out = Path("outputs/reports/model1_gaze/confusion_matrix.png")
        ensure_dir(out.parent)
        fig.savefig(out, dpi=120)
        plt.close(fig)
        print(f"  {PASS} Saved confusion matrix → {out}")
    except Exception as e:
        print(f"  [warn] Could not save plot: {e}")

    status = PASS if f1 > 0.4 else FAIL
    print(f"\n  {status} Model 1 | acc={acc:.4f} | macro-F1={f1:.4f}")
    return {"accuracy": acc, "macro_f1": f1}


# ─── Model 2 · Pose ──────────────────────────────────────────────────────────

def test_model2_pose():
    sep("Model 2 · Head Pose Regression (ResNet-18)")

    ckpt_path = Path("outputs/checkpoints/model2_pose/best.pt")
    test_csv  = Path("data/processed/model2_pose/test.csv")

    if not ckpt_path.exists():
        print(f"  {SKIP} Checkpoint not found: {ckpt_path}")
        return
    if not test_csv.exists():
        print(f"  {SKIP} Test CSV not found: {test_csv}")
        return

    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, Dataset
    from torchvision import transforms, models
    from PIL import Image
    from tqdm import tqdm

    class PoseDataset(Dataset):
        def __init__(self, csv_path, img_size=224):
            self.df = pd.read_csv(csv_path)
            self.tf = transforms.Compose([
                transforms.Resize((img_size, img_size)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ])
        def __len__(self): return len(self.df)
        def __getitem__(self, i):
            r = self.df.iloc[i]
            x = self.tf(Image.open(r["img_path"]).convert("RGB"))
            y = torch.tensor([r["yaw_deg"], r["pitch_deg"], r["roll_deg"]], dtype=torch.float32)
            return x, y

    device = "cpu"   # CPU-only: safe, lightweight

    ds = PoseDataset(test_csv)
    dl = DataLoader(ds, batch_size=128, shuffle=False, num_workers=0,
                    pin_memory=False)

    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    epoch_trained = ckpt.get("epoch", "?")
    best_val      = ckpt.get("best_val", "?")

    m = models.resnet18(weights=None)
    m.fc = nn.Linear(m.fc.in_features, 3)
    state = {k.replace("net.", ""): v for k, v in ckpt["model"].items()}
    m.load_state_dict(state)
    m.eval()

    if isinstance(best_val, float):
        print(f"  Checkpoint epoch : {epoch_trained}  |  best val loss: {best_val:.4f}")
    else:
        print(f"  Checkpoint epoch : {epoch_trained}")
    print(f"  Test samples     : {len(ds):,}")
    print("  Running on CPU... ", end="", flush=True)

    mae_sum = torch.zeros(3)
    mse_sum = torch.zeros(3)
    n = 0

    with torch.no_grad():
        for i, (x, y) in enumerate(dl):
            p        = m(x)
            mae_sum += (p - y).abs().sum(dim=0)
            mse_sum += ((p - y) ** 2).sum(dim=0)
            n        += x.size(0)
            if (i + 1) % 5 == 0:
                print(".", end="", flush=True)
    print(" done")

    mae  = (mae_sum / n).numpy()
    rmse = ((mse_sum / n) ** 0.5).numpy()

    print(f"\n  {'Angle':<10}  {'MAE (deg)':>10}  {'RMSE (deg)':>12}")
    print(f"  {'─'*10}  {'─'*10}  {'─'*12}")
    for i, angle in enumerate(["Yaw", "Pitch", "Roll"]):
        ok = PASS if mae[i] < 15 else FAIL
        print(f"  {angle:<10}  {mae[i]:>10.2f}  {rmse[i]:>12.2f}  {ok}")

    overall_mae = float(np.mean(mae))
    status = PASS if overall_mae < 15 else FAIL
    print(f"\n  {status} Model 2 | Mean MAE = {overall_mae:.2f} deg")
    return {"mae_yaw": float(mae[0]), "mae_pitch": float(mae[1]), "mae_roll": float(mae[2])}


# ─── Model 4 · Engagement ────────────────────────────────────────────────────

def test_model4_engagement():
    sep("Model 4 · Engagement Classifier (Logistic Regression)")

    ckpt_path = Path("outputs/checkpoints/model4_engagement/model.pkl")
    labeled_csv = Path("data/processed/model4_engagement/labeled.csv")

    if not ckpt_path.exists():
        print(f"  {SKIP} Checkpoint not found: {ckpt_path}")
        return
    if not labeled_csv.exists():
        print(f"  {SKIP} Labeled CSV not found: {labeled_csv}")
        return

    from sklearn.metrics import (
        classification_report, confusion_matrix,
        accuracy_score, f1_score, roc_auc_score
    )
    from sklearn.model_selection import train_test_split

    pack  = joblib.load(ckpt_path)
    model = pack["model"]
    cols  = pack["feature_cols"]

    df = pd.read_csv(labeled_csv).dropna(subset=["active_work"])
    X  = df[cols].fillna(0.0).to_numpy().astype(np.float32)
    y  = df["active_work"].to_numpy().astype(int)

    # Recreate the same 25% test split used at training time
    _, X_te, _, y_te = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

    y_pred = model.predict(X_te)
    y_prob = model.predict_proba(X_te)[:, 1]

    acc = accuracy_score(y_te, y_pred)
    f1  = f1_score(y_te, y_pred, average="macro")
    try:
        auc = roc_auc_score(y_te, y_prob)
    except Exception:
        auc = float("nan")

    print(f"  Features used: {len(cols)}")
    print(f"  Test samples : {len(y_te):,}")
    print(f"\n  Test Accuracy  : {acc:.4f}  ({acc*100:.1f}%)")
    print(f"  Macro F1 Score : {f1:.4f}")
    print(f"  ROC-AUC        : {auc:.4f}")
    print()
    print(classification_report(y_te, y_pred,
                                target_names=["inactive", "active_work"], digits=4))

    cm = confusion_matrix(y_te, y_pred)
    print("  Confusion Matrix:")
    print(f"           inactive  active")
    print(f"  inactive  {cm[0,0]:>6}  {cm[0,1]:>6}")
    print(f"  active    {cm[1,0]:>6}  {cm[1,1]:>6}")

    status = PASS if f1 > 0.5 else FAIL
    print(f"\n  {status} Model 4 | acc={acc:.4f} | macro-F1={f1:.4f} | ROC-AUC={auc:.4f}")
    return {"accuracy": acc, "macro_f1": f1, "roc_auc": auc}


# ─── Model 5 · Fusion ────────────────────────────────────────────────────────

def test_model5_fusion():
    sep("Model 5 · Fusion Classifier (Logistic Regression)")

    ckpt_path = Path("outputs/checkpoints/model5_fusion/model.pkl")
    test_csv  = Path("data/processed/model5_fusion/test.csv")

    if not ckpt_path.exists():
        print(f"  {SKIP} Checkpoint not found: {ckpt_path}")
        return
    if not test_csv.exists():
        print(f"  {SKIP} Test CSV not found: {test_csv}")
        return

    from sklearn.metrics import (
        classification_report, confusion_matrix,
        accuracy_score, f1_score, precision_score,
        recall_score, roc_auc_score, average_precision_score
    )

    pack      = joblib.load(ckpt_path)
    model     = pack["model"]
    feats     = pack["features"]
    threshold = float(pack.get("threshold", 0.5))
    tuning    = pack.get("threshold_tuning", {})

    df   = pd.read_csv(test_csv)
    X_te = df[feats].fillna(0.0).to_numpy().astype(np.float32)
    y_te = df["y"].to_numpy().astype(int)

    prob   = model.predict_proba(X_te)[:, 1]
    y_pred_05  = (prob >= 0.5).astype(int)
    y_pred_thr = (prob >= threshold).astype(int)

    def metrics(y_true, y_pred, y_prob):
        acc  = accuracy_score(y_true, y_pred)
        f1   = f1_score(y_true, y_pred, zero_division=0)
        prec = precision_score(y_true, y_pred, zero_division=0)
        rec  = recall_score(y_true, y_pred, zero_division=0)
        try:
            auc = roc_auc_score(y_true, y_prob)
            pr  = average_precision_score(y_true, y_prob)
        except Exception:
            auc, pr = float("nan"), float("nan")
        return acc, f1, prec, rec, auc, pr

    print(f"  Features used : {len(feats)}")
    print(f"  Threshold     : {threshold:.3f}  (tuned: {tuning.get('enabled', False)})")
    print(f"  Test samples  : {len(y_te):,}  |  distracted: {y_te.sum()}  focused: {(1-y_te).sum()}")

    print(f"\n  ── At default threshold = 0.50 ──")
    acc, f1, prec, rec, auc, pr = metrics(y_te, y_pred_05, prob)
    print(f"  Accuracy={acc:.4f}  F1={f1:.4f}  Prec={prec:.4f}  Rec={rec:.4f}")
    print(f"  ROC-AUC={auc:.4f}  PR-AUC={pr:.4f}")
    print(classification_report(y_te, y_pred_05,
                                target_names=["focused","distracted"], digits=4))

    # Always define f1 at the stored threshold (may equal 0.5 when untuned).
    acc_thr, f1_thr, prec_thr, rec_thr, _, _ = metrics(y_te, y_pred_thr, prob)
    if abs(threshold - 0.5) > 0.01:
        print(f"\n  ── At tuned threshold = {threshold:.3f} ──")
        print(f"  Accuracy={acc_thr:.4f}  F1={f1_thr:.4f}  Prec={prec_thr:.4f}  Rec={rec_thr:.4f}")
        print(classification_report(y_te, y_pred_thr,
                                    target_names=["focused","distracted"], digits=4))

    cm = confusion_matrix(y_te, y_pred_thr)
    print(f"  Confusion Matrix (threshold={threshold:.3f}):")
    print(f"              focused  distracted")
    print(f"  focused     {cm[0,0]:>7}  {cm[0,1]:>10}")
    print(f"  distracted  {cm[1,0]:>7}  {cm[1,1]:>10}")

    status = PASS if auc > 0.5 else FAIL
    print(
        f"\n  {status} Model 5 | ROC-AUC={auc:.4f} | F1@0.5={f1:.4f} "
        f"| F1@{threshold:.2f}={f1_thr:.4f}"
    )
    return {"roc_auc": auc, "f1_default": f1, "f1_tuned": f1_thr}


# ─── Entry point ─────────────────────────────────────────────────────────────

MODEL_MAP = {
    "gaze":       test_model1_gaze,
    "pose":       test_model2_pose,
    "engagement": test_model4_engagement,
    "fusion":     test_model5_fusion,
}

def main():
    ap = argparse.ArgumentParser(description="Evaluate all distraction detection models")
    ap.add_argument("--model", choices=list(MODEL_MAP.keys()),
                    default=None,
                    help="Which model to test (default: all)")
    args = ap.parse_args()

    print("=" * 60)
    print("  DISTRACTION MODEL — TEST SUITE")
    print("=" * 60)

    to_run = [args.model] if args.model else list(MODEL_MAP.keys())
    results = {}

    for key in to_run:
        try:
            r = MODEL_MAP[key]()
            if r:
                results[key] = r
        except Exception as e:
            print(f"\n  {FAIL} {key} crashed: {e}")
            import traceback; traceback.print_exc()

    # ── Summary ────────────────────────────────────────────────────────────
    sep("SUMMARY")
    rows = [
        ("gaze",       "Model 1 · Gaze",
         lambda r: f"acc={r['accuracy']:.4f} | macro-F1={r['macro_f1']:.4f}"),
        ("pose",       "Model 2 · Pose",
         lambda r: f"MAE  yaw={r['mae_yaw']:.2f}°  pitch={r['mae_pitch']:.2f}°  roll={r['mae_roll']:.2f}°"),
        ("engagement", "Model 4 · Engagement",
         lambda r: f"acc={r['accuracy']:.4f} | macro-F1={r['macro_f1']:.4f} | AUC={r['roc_auc']:.4f}"),
        ("fusion",     "Model 5 · Fusion",
         lambda r: f"ROC-AUC={r['roc_auc']:.4f} | F1@0.5={r['f1_default']:.4f} | F1@tuned={r['f1_tuned']:.4f}"),
    ]
    for key, label, fmt in rows:
        if key in results:
            icon = PASS
            print(f"  {icon} {label:<22} | {fmt(results[key])}")
        elif key in to_run:
            print(f"  {FAIL} {label:<22} | crashed or skipped")
    sep()

if __name__ == "__main__":
    main()
