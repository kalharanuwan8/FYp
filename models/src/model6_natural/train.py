"""GPU leave-one-subject-out fusion training (PyTorch CUDA)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    f1_score,
    roc_auc_score,
    average_precision_score,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from models.src.features.windows import WINDOW_FEATURE_NAMES  # noqa: E402
from models.src.model6_natural.wrapper import FusionMLP, Model6SklearnWrapper  # noqa: E402

HONEST_BASELINE_ROC = 0.77
HONEST_BASELINE_F1 = 0.54


@dataclass
class FoldMetrics:
    subject_id: str
    n_train: int
    n_test: int
    accuracy: float
    f1_positive: float
    f1_macro: float
    roc_auc: float
    pr_auc: float
    threshold: float
    false_alarms_per_min_natural: float
    natural_n: int
    natural_pred_positive: int
    baseline_lr_f1_positive: float
    baseline_lr_roc_auc: float


def _require_cuda() -> torch.device:
    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is required for model6 training. "
            "torch.cuda.is_available() is False — refusing CPU fallback."
        )
    name = torch.cuda.get_device_name(0)
    print(f"[train] device=cuda ({name})")
    return torch.device("cuda")


def _xy(df: pd.DataFrame, feats: List[str]) -> Tuple[np.ndarray, np.ndarray]:
    X = df[feats].fillna(0.0).astype(np.float32).values
    y = df["y"].astype(int).values
    return X, y


def _metrics(y_true: np.ndarray, proba: np.ndarray, thr: float) -> Dict[str, float]:
    pred = (proba >= thr).astype(int)
    acc = float(np.mean(pred == y_true)) if len(y_true) else float("nan")
    f1_pos = float(f1_score(y_true, pred, pos_label=1, zero_division=0))
    f1_mac = float(f1_score(y_true, pred, average="macro", zero_division=0))
    roc = float("nan")
    pr = float("nan")
    if len(np.unique(y_true)) > 1:
        roc = float(roc_auc_score(y_true, proba))
        pr = float(average_precision_score(y_true, proba))
    return {
        "accuracy": acc,
        "f1_positive": f1_pos,
        "f1_macro": f1_mac,
        "roc_auc": roc,
        "pr_auc": pr,
    }


def _pick_threshold(y_true: np.ndarray, proba: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return 0.5
    best_t, best_f1 = 0.5, -1.0
    for t in np.linspace(0.2, 0.8, 61):
        pred = (proba >= t).astype(int)
        f1 = f1_score(y_true, pred, pos_label=1, zero_division=0)
        if f1 > best_f1:
            best_f1 = float(f1)
            best_t = float(t)
    return best_t


def _false_alarms_per_min(natural_df: pd.DataFrame, proba: np.ndarray, thr: float) -> Tuple[float, int, int]:
    """Count positive predictions on natural clip as false alarms / minute."""
    if natural_df.empty:
        return float("nan"), 0, 0
    pred = (proba >= thr).astype(int)
    n_pos = int(pred.sum())
    # Duration from window starts of the longer window size if mixed; use span
    t0 = float(natural_df["window_start_sec"].min())
    t1 = float(natural_df["window_start_sec"].max() + natural_df["window_sec"].max())
    minutes = max((t1 - t0) / 60.0, 1e-6)
    return float(n_pos / minutes), int(len(natural_df)), n_pos


def train_mlp_fold(
    Xtr: np.ndarray,
    ytr: np.ndarray,
    Xte: np.ndarray,
    device: torch.device,
    epochs: int = 80,
    batch_size: int = 64,
    lr: float = 1e-3,
) -> Tuple[FusionMLP, StandardScaler, np.ndarray]:
    scaler = StandardScaler()
    Xtr_s = scaler.fit_transform(Xtr).astype(np.float32)
    Xte_s = scaler.transform(Xte).astype(np.float32)

    model = FusionMLP(n_in=Xtr_s.shape[1]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    # class balance
    n_pos = max(int((ytr == 1).sum()), 1)
    n_neg = max(int((ytr == 0).sum()), 1)
    pos_weight = torch.tensor([n_neg / n_pos], device=device, dtype=torch.float32)
    crit = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    ds = TensorDataset(
        torch.from_numpy(Xtr_s),
        torch.from_numpy(ytr.astype(np.float32)),
    )
    loader = DataLoader(ds, batch_size=batch_size, shuffle=True, drop_last=False)

    use_amp = True
    scaler_amp = torch.amp.GradScaler("cuda", enabled=use_amp)

    model.train()
    for epoch in range(epochs):
        total = 0.0
        for xb, yb in loader:
            xb = xb.to(device, non_blocking=True)
            yb = yb.to(device, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=use_amp):
                logits = model(xb)
                loss = crit(logits, yb)
            scaler_amp.scale(loss).backward()
            scaler_amp.step(opt)
            scaler_amp.update()
            total += float(loss.item()) * len(xb)
        if (epoch + 1) % 20 == 0:
            print(f"    epoch {epoch+1}/{epochs} loss={total / max(len(ds),1):.4f}")

    model.eval()
    with torch.no_grad():
        xt = torch.from_numpy(Xte_s).to(device)
        with torch.amp.autocast("cuda", enabled=use_amp):
            logits = model(xt)
        proba = torch.sigmoid(logits.float()).cpu().numpy()
    return model, scaler, proba


def run_loso(
    windows_csv: Path,
    out_dir: Path,
    ckpt_dir: Path,
    epochs: int,
    window_sec_filter: Optional[float],
) -> dict:
    device = _require_cuda()
    df = pd.read_csv(windows_csv)
    feats = list(WINDOW_FEATURE_NAMES)
    for c in feats + ["subject_id", "y", "condition", "in_train"]:
        if c not in df.columns:
            raise ValueError(f"windows.csv missing column: {c}")

    if window_sec_filter is not None:
        df = df[np.isclose(df["window_sec"], window_sec_filter)].copy()
        print(f"[train] filtering window_sec={window_sec_filter} → {len(df)} rows")

    train_df = df[df["in_train"] == 1].copy()
    natural_df = df[df["condition"] == "natural"].copy()
    subjects = sorted(train_df["subject_id"].unique().tolist())
    if len(subjects) < 2:
        raise RuntimeError(f"Need ≥2 subjects with train labels, got {subjects}")

    fold_rows: List[dict] = []
    best_pack = None
    best_mean_f1 = -1.0

    for held in subjects:
        print(f"\n[train] LOSO hold-out {held}")
        tr = train_df[train_df["subject_id"] != held]
        te = train_df[train_df["subject_id"] == held]
        if tr.empty or te.empty:
            print(f"  skip {held}: empty train/test")
            continue
        if len(tr["y"].unique()) < 2:
            print(f"  skip {held}: train has one class")
            continue

        Xtr, ytr = _xy(tr, feats)
        Xte, yte = _xy(te, feats)

        # CPU logistic baseline on same fold
        lr = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(max_iter=2000, class_weight="balanced", solver="lbfgs"),
                ),
            ]
        )
        lr.fit(Xtr, ytr)
        lr_proba = lr.predict_proba(Xte)[:, 1]
        lr_thr = _pick_threshold(yte, lr_proba)
        lr_m = _metrics(yte, lr_proba, lr_thr)

        model, scaler, proba = train_mlp_fold(Xtr, ytr, Xte, device, epochs=epochs)
        thr = _pick_threshold(yte, proba)
        m = _metrics(yte, proba, thr)

        # Natural false alarms for held-out subject
        nat = natural_df[natural_df["subject_id"] == held]
        fa_rate, nat_n, nat_pos = float("nan"), 0, 0
        if not nat.empty:
            Xn = nat[feats].fillna(0.0).astype(np.float32).values
            Xn_s = scaler.transform(Xn).astype(np.float32)
            model.eval()
            with torch.no_grad():
                xt = torch.from_numpy(Xn_s).to(device)
                with torch.amp.autocast("cuda"):
                    logits = model(xt)
                nat_proba = torch.sigmoid(logits.float()).cpu().numpy()
            fa_rate, nat_n, nat_pos = _false_alarms_per_min(nat, nat_proba, thr)

        fold = FoldMetrics(
            subject_id=held,
            n_train=int(len(tr)),
            n_test=int(len(te)),
            accuracy=m["accuracy"],
            f1_positive=m["f1_positive"],
            f1_macro=m["f1_macro"],
            roc_auc=m["roc_auc"],
            pr_auc=m["pr_auc"],
            threshold=thr,
            false_alarms_per_min_natural=fa_rate,
            natural_n=nat_n,
            natural_pred_positive=nat_pos,
            baseline_lr_f1_positive=lr_m["f1_positive"],
            baseline_lr_roc_auc=lr_m["roc_auc"],
        )
        fold_rows.append(fold.__dict__)
        print(
            f"  MLP F1+={fold.f1_positive:.3f} ROC={fold.roc_auc:.3f} "
            f"thr={fold.threshold:.3f} FA/min={fold.false_alarms_per_min_natural:.2f} | "
            f"LR F1+={fold.baseline_lr_f1_positive:.3f} ROC={fold.baseline_lr_roc_auc:.3f}"
        )

        # Keep pack from fold with best F1 for deployment candidate
        # Retrain on all-but-held already done; store state
        pack = {
            "kind": "model6_mlp",
            "features": feats,
            "threshold": float(thr),
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist(),
            "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
            "hidden": 64,
            "held_out_subject": held,
            "window_sec_filter": window_sec_filter,
        }
        if fold.f1_positive > best_mean_f1:
            best_mean_f1 = fold.f1_positive
            best_pack = pack

    if not fold_rows:
        raise RuntimeError("No LOSO folds completed")

    def _nanmean(key):
        vals = [r[key] for r in fold_rows if r[key] == r[key]]
        return float(np.mean(vals)) if vals else float("nan")

    summary = {
        "folds": fold_rows,
        "mean": {
            "f1_positive": _nanmean("f1_positive"),
            "f1_macro": _nanmean("f1_macro"),
            "roc_auc": _nanmean("roc_auc"),
            "accuracy": _nanmean("accuracy"),
            "false_alarms_per_min_natural": _nanmean("false_alarms_per_min_natural"),
            "baseline_lr_f1_positive": _nanmean("baseline_lr_f1_positive"),
            "baseline_lr_roc_auc": _nanmean("baseline_lr_roc_auc"),
        },
        "honest_baseline": {"roc_auc": HONEST_BASELINE_ROC, "f1_positive": HONEST_BASELINE_F1},
        "beats_honest_baseline": bool(
            _nanmean("roc_auc") > HONEST_BASELINE_ROC
            and _nanmean("f1_positive") > HONEST_BASELINE_F1
        ),
        "device": torch.cuda.get_device_name(0),
        "windows_csv": str(windows_csv),
        "n_subjects": len(subjects),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "loso_metrics.json"
    metrics_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n[train] wrote {metrics_path}")
    print(
        f"[train] mean F1+={summary['mean']['f1_positive']:.3f} "
        f"ROC={summary['mean']['roc_auc']:.3f} "
        f"beats_honest={summary['beats_honest_baseline']}"
    )

    # Final deploy pack: retrain on ALL labeled windows if we beat baseline
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    if summary["beats_honest_baseline"] and best_pack is not None:
        Xall, yall = _xy(train_df, feats)
        # Use a tiny held-out from last fold just for threshold; retrain full
        model, scaler, _ = train_mlp_fold(
            Xall, yall, Xall[: min(32, len(Xall))], device, epochs=epochs
        )
        # Threshold from mean of fold thresholds
        thr = float(np.mean([r["threshold"] for r in fold_rows]))
        deploy = {
            "kind": "model6_mlp",
            "features": feats,
            "threshold": thr,
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist(),
            "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
            "hidden": 64,
            "metrics_mean": summary["mean"],
            "deploy": True,
        }
        # sklearn-compatible wrapper saved via joblib for ml_service
        wrapper = Model6SklearnWrapper(deploy)
        pack_path = ckpt_dir / "model.pkl"
        joblib.dump(
            {
                "model": wrapper,
                "threshold": thr,
                "features": feats,
                "kind": "model6_mlp",
                "metrics_mean": summary["mean"],
            },
            pack_path,
        )
        torch.save(deploy, ckpt_dir / "model6_mlp.pt")
        summary["deployed"] = True
        summary["checkpoint"] = str(pack_path)
        print(f"[train] DEPLOYED {pack_path}")
    else:
        # Still save the best fold pack for inspection, but mark not deployed
        if best_pack is not None:
            inspect_path = ckpt_dir / "model6_mlp_best_fold.pt"
            torch.save(best_pack, inspect_path)
            summary["deployed"] = False
            summary["checkpoint_inspect"] = str(inspect_path)
            print(
                "[train] did not beat honest baseline — "
                f"left model5 fusion in place; inspect pack at {inspect_path}"
            )
        else:
            summary["deployed"] = False

    metrics_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description="Train model6 fusion on CUDA (LOSO)")
    p.add_argument(
        "--windows",
        type=Path,
        default=_REPO / "models" / "data" / "processed" / "model6_natural" / "windows.csv",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=_REPO / "models" / "reports" / "model6_natural",
    )
    p.add_argument(
        "--ckpt-dir",
        type=Path,
        default=_REPO / "models" / "outputs" / "checkpoints" / "model6_natural",
    )
    p.add_argument("--epochs", type=int, default=80)
    p.add_argument(
        "--window-sec",
        type=float,
        default=5.0,
        help="Train on this window length only (default 5s). Use 0 for all.",
    )
    args = p.parse_args(argv)
    wfilter = None if args.window_sec <= 0 else float(args.window_sec)
    if not args.windows.exists():
        raise FileNotFoundError(
            f"Missing {args.windows}. Run: python -m models.src.model6_natural.extract"
        )
    run_loso(args.windows, args.out_dir, args.ckpt_dir, args.epochs, wfilter)


if __name__ == "__main__":
    main()
