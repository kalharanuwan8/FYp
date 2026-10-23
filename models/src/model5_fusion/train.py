from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Any, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
)


# -----------------------------
# IO helpers
# -----------------------------
def _load_meta(meta_path: Path) -> list[str]:
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing meta.json: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    feats = meta.get("features")
    if not feats or not isinstance(feats, list):
        raise ValueError("meta.json must contain a list field: 'features'")
    return feats


def _print_split_stats(name: str, df: pd.DataFrame):
    print(f"\n== {name} ==")
    print("rows:", len(df))
    if "y" not in df.columns:
        print("ERROR: missing 'y' column")
        return
    vc = df["y"].value_counts().to_dict()
    print("class counts:", vc)


def _safe_report(name: str, y_true: np.ndarray, y_pred: np.ndarray):
    uniq = np.unique(y_true)
    print(f"\n--- {name} report ---")
    if len(uniq) < 2:
        print(f"Warning: {name} set has only one class {uniq.tolist()}.")
        print("Classification report is not meaningful. Fix the split in prep/prepare.")
        print("Pred counts:", pd.Series(y_pred).value_counts().to_dict())
        return
    print(classification_report(y_true, y_pred, digits=4))
    print("Confusion matrix:\n", confusion_matrix(y_true, y_pred))


def _safe_auc_metrics(name: str, y_true: np.ndarray, proba_1: np.ndarray):
    """
    Prints ROC-AUC and PR-AUC safely (only if both classes exist).
    """
    uniq = np.unique(y_true)
    if len(uniq) < 2:
        print(f"{name} AUC metrics skipped (only one class present).")
        return

    try:
        roc = roc_auc_score(y_true, proba_1)
    except Exception:
        roc = None

    try:
        pr = average_precision_score(y_true, proba_1)
    except Exception:
        pr = None

    msg = []
    if roc is not None:
        msg.append(f"ROC-AUC: {roc:.4f}")
    if pr is not None:
        msg.append(f"PR-AUC: {pr:.4f}")

    if msg:
        print(f"{name} " + " | ".join(msg))


# -----------------------------
# Threshold tuning
# -----------------------------
def _pick_threshold(
    y_true: np.ndarray,
    proba_1: np.ndarray,
    metric: str = "f1",
    t_min: float = 0.05,
    t_max: float = 0.95,
    steps: int = 181,
) -> Dict[str, float]:
    """
    Picks threshold that maximizes chosen metric on validation.
    metric in {"f1","precision","recall"}.
    """
    uniq = np.unique(y_true)
    if len(uniq) < 2:
        # can't tune threshold if val has one class
        return {"threshold": 0.5, "score": float("nan"), "precision": float("nan"), "recall": float("nan"), "f1": float("nan")}

    best = None
    for t in np.linspace(t_min, t_max, steps):
        pred = (proba_1 >= t).astype(int)
        p = precision_score(y_true, pred, zero_division=0)
        r = recall_score(y_true, pred, zero_division=0)
        f1 = f1_score(y_true, pred, zero_division=0)

        if metric == "precision":
            score = p
        elif metric == "recall":
            score = r
        else:
            score = f1

        if best is None or score > best["score"]:
            best = {"threshold": float(t), "score": float(score), "precision": float(p), "recall": float(r), "f1": float(f1)}

    return best if best is not None else {"threshold": 0.5, "score": float("nan"), "precision": float("nan"), "recall": float("nan"), "f1": float("nan")}


# -----------------------------
# Main train
# -----------------------------
def train(
    data_dir: Path,
    out_model: Path,
    max_iter: int = 2000,
    C: float = 1.0,
    use_class_weight_balanced: bool = False,
    tune_threshold: bool = True,
    threshold_metric: str = "f1",
):
    train_csv = data_dir / "train.csv"
    val_csv = data_dir / "val.csv"
    meta_json = data_dir / "meta.json"

    if not train_csv.exists():
        raise FileNotFoundError(f"Missing: {train_csv}")
    if not val_csv.exists():
        raise FileNotFoundError(f"Missing: {val_csv}")

    feats = _load_meta(meta_json)

    df_tr = pd.read_csv(train_csv)
    df_va = pd.read_csv(val_csv)

    _print_split_stats("TRAIN", df_tr)
    _print_split_stats("VAL", df_va)

    # checks
    for c in feats + ["y"]:
        if c not in df_tr.columns:
            raise ValueError(f"train.csv missing column: {c}")
    for c in feats + ["y"]:
        if c not in df_va.columns:
            raise ValueError(f"val.csv missing column: {c}")

    # features/labels
    Xtr = df_tr[feats].fillna(0.0).values.astype(np.float32)
    ytr = df_tr["y"].values.astype(int)

    Xva = df_va[feats].fillna(0.0).values.astype(np.float32)
    yva = df_va["y"].values.astype(int)

    # train must have 2 classes
    if len(np.unique(ytr)) < 2:
        raise RuntimeError(
            "TRAIN has only one class. Fusion training is impossible.\n"
            "Fix your weak-label thresholds or your split in prep/prepare."
        )

    cw = "balanced" if use_class_weight_balanced else None

    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(
            max_iter=max_iter,
            C=C,
            class_weight=cw,
            solver="lbfgs",
        ))
    ])

    clf.fit(Xtr, ytr)

    # Probabilities
    proba_tr = clf.predict_proba(Xtr)[:, 1]
    proba_va = clf.predict_proba(Xva)[:, 1]

    # Default threshold 0.5
    pred_tr_05 = (proba_tr >= 0.5).astype(int)
    pred_va_05 = (proba_va >= 0.5).astype(int)

    print("\n### Using default threshold = 0.50 ###")
    _safe_report("TRAIN", ytr, pred_tr_05)
    _safe_report("VAL", yva, pred_va_05)
    _safe_auc_metrics("TRAIN", ytr, proba_tr)
    _safe_auc_metrics("VAL", yva, proba_va)

    # Tune threshold on VAL
    chosen_threshold = 0.5
    thresh_info = None

    if tune_threshold:
        thresh_info = _pick_threshold(yva, proba_va, metric=threshold_metric)
        chosen_threshold = float(thresh_info["threshold"])

        pred_tr_t = (proba_tr >= chosen_threshold).astype(int)
        pred_va_t = (proba_va >= chosen_threshold).astype(int)

        print(f"\n### Tuned threshold on VAL ({threshold_metric}) = {chosen_threshold:.3f} ###")
        print(f"VAL best score: {thresh_info['score']:.4f} | "
              f"P={thresh_info['precision']:.4f} R={thresh_info['recall']:.4f} F1={thresh_info['f1']:.4f}")

        _safe_report("TRAIN", ytr, pred_tr_t)
        _safe_report("VAL", yva, pred_va_t)

    # Save model package
    out_model.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "model": clf,
        "features": feats,
        "threshold": chosen_threshold,
        "class_weight": cw,
        "C": C,
        "max_iter": max_iter,
        "threshold_tuning": {
            "enabled": bool(tune_threshold),
            "metric": threshold_metric,
            "val_best": thresh_info,
        },
    }
    joblib.dump(payload, out_model)
    print(f"\nSaved: {out_model}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/processed/model5_fusion", type=str)
    ap.add_argument("--out", default="outputs/checkpoints/model5_fusion/model.pkl", type=str)
    ap.add_argument("--max-iter", default=2000, type=int)
    ap.add_argument("--C", default=1.0, type=float)

    # IMPORTANT: your current code had class_weight="balanced" ON.
    # That often causes the "predict 1 too much" problem you saw.
    ap.add_argument("--balanced", action="store_true", help="Use class_weight='balanced'")

    ap.add_argument("--tune-threshold", action="store_true", help="Tune threshold on VAL (recommended)")
    ap.add_argument("--threshold-metric", default="f1", choices=["f1", "precision", "recall"])

    args = ap.parse_args()

    train(
        data_dir=Path(args.data_dir),
        out_model=Path(args.out),
        max_iter=args.max_iter,
        C=args.C,
        use_class_weight_balanced=bool(args.balanced),
        tune_threshold=bool(args.tune_threshold),
        threshold_metric=args.threshold_metric,
    )


if __name__ == "__main__":
    main()
