"""
Leave-one-participant-out training for M4 on extract_participants windows.

Fits StandardScaler + LogisticRegression on the 9 late-fusion features,
reports metrics at 0.5 and 0.75, compares the previous weak-label M4, and
scores natural videos as a sanity check. Writes the final all-participant
model to checkpoints_late_fusion/model5_fusion/model.pkl (after backing up
the weak-label pack).

Usage (from the models/ directory):
  ..\\venvpy312\\Scripts\\python.exe -u -m src.model5_fusion.train_loso
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

MODELS = Path(__file__).resolve().parents[2]
DATA = MODELS / "data" / "processed" / "model5_fusion_participants"
STAGE = MODELS / "outputs" / "checkpoints_late_fusion" / "model5_fusion"
LOG_DIR = MODELS / "outputs" / "logs" / "model5_fusion_participants"

FEAT_COLS = [
    "p_center_mean",
    "p_left_mean",
    "p_right_mean",
    "p_down_mean",
    "gaze_away_ratio",
    "yaw_mean",
    "pitch_mean",
    "roll_mean",
    "engagement_prob_mean",
]
THRESHOLDS = (0.5, 0.75)


def _metrics(y_true, proba, thr: float) -> Dict[str, float]:
    pred = (proba >= thr).astype(int)
    out = {
        "n": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, pred)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "pos_rate": float(pred.mean()) if len(pred) else 0.0,
        "true_pos_rate": float(np.mean(y_true)) if len(y_true) else 0.0,
    }
    if len(np.unique(y_true)) >= 2:
        out["roc_auc"] = float(roc_auc_score(y_true, proba))
    else:
        out["roc_auc"] = float("nan")
    return out


def _fit_pipe(X: np.ndarray, y: np.ndarray) -> Pipeline:
    pipe = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "lr",
                LogisticRegression(
                    C=1.0,
                    solver="lbfgs",
                    max_iter=2000,
                    random_state=42,
                ),
            ),
        ]
    )
    pipe.fit(X, y)
    return pipe


def _proba(pipe: Pipeline, X: np.ndarray) -> np.ndarray:
    return pipe.predict_proba(X)[:, 1]


def main() -> None:
    windows_path = DATA / "windows.csv"
    if not windows_path.exists():
        raise SystemExit(f"Missing {windows_path}; run extract_participants first")

    df = pd.read_csv(windows_path)
    for c in FEAT_COLS + ["y", "participant", "video"]:
        if c not in df.columns:
            raise SystemExit(f"windows.csv missing column {c}")

    labelled = df[df["y"].isin([0, 1])].copy()
    natural = df[df["video"].str.lower() == "natural"].copy()
    labelled["y"] = labelled["y"].astype(int)

    participants = sorted(labelled["participant"].unique())
    print(
        f"[loso] labelled={len(labelled)} natural={len(natural)} "
        f"participants={participants}"
    )
    print(
        "class counts:",
        labelled["y"].value_counts().to_dict(),
        "by participant:",
        {
            p: labelled.loc[labelled["participant"] == p, "y"].value_counts().to_dict()
            for p in participants
        },
    )

    fold_rows: List[Dict] = []
    pooled_y: List[int] = []
    pooled_p: List[float] = []
    per_participant: Dict[str, Dict] = {}

    for hold in participants:
        train = labelled[labelled["participant"] != hold]
        test = labelled[labelled["participant"] == hold]
        if len(train) == 0 or len(test) == 0:
            print(f"  skip fold {hold}: empty")
            continue
        if train["y"].nunique() < 2:
            print(f"  skip fold {hold}: train has one class")
            continue

        Xtr = train[FEAT_COLS].to_numpy(dtype=np.float64)
        ytr = train["y"].to_numpy(dtype=int)
        Xte = test[FEAT_COLS].to_numpy(dtype=np.float64)
        yte = test["y"].to_numpy(dtype=int)

        pipe = _fit_pipe(Xtr, ytr)
        proba = _proba(pipe, Xte)
        pooled_y.extend(yte.tolist())
        pooled_p.extend(proba.tolist())

        fold = {"holdout": hold, "n_train": int(len(train)), "n_test": int(len(test))}
        for thr in THRESHOLDS:
            fold[f"thr_{thr}"] = _metrics(yte, proba, thr)
        fold_rows.append(fold)
        per_participant[hold] = fold
        print(
            f"  holdout {hold}: n={len(test)} "
            f"F1@0.75={fold['thr_0.75']['f1']:.3f} "
            f"acc@0.75={fold['thr_0.75']['accuracy']:.3f} "
            f"auc={fold['thr_0.75']['roc_auc']:.3f}"
        )

    y_all = np.asarray(pooled_y, dtype=int)
    p_all = np.asarray(pooled_p, dtype=float)
    pooled = {f"thr_{thr}": _metrics(y_all, p_all, thr) for thr in THRESHOLDS}
    print("\n[loso] pooled:")
    for thr in THRESHOLDS:
        m = pooled[f"thr_{thr}"]
        print(
            f"  thr={thr}: acc={m['accuracy']:.3f} P={m['precision']:.3f} "
            f"R={m['recall']:.3f} F1={m['f1']:.3f} AUC={m['roc_auc']:.3f}"
        )

    # Baseline: previous weak-label M4 on the same held-out labelled windows.
    old_path = STAGE / "model.pkl"
    baseline = None
    if old_path.exists():
        old = joblib.load(old_path)
        old_model = old["model"] if isinstance(old, dict) else old
        old_feats = list(old.get("features", FEAT_COLS)) if isinstance(old, dict) else FEAT_COLS
        use = [c for c in old_feats if c in FEAT_COLS]
        if hasattr(old_model, "predict_proba") and use:
            # Score each fold's holdout with the fixed old model (not re-fit).
            by = labelled["y"].to_numpy(dtype=int)
            bp = _proba(old_model, labelled[use].to_numpy(dtype=np.float64))
            baseline = {
                f"thr_{thr}": _metrics(by, bp, thr) for thr in THRESHOLDS
            }
            print("\n[baseline] weak-label M4 on all labelled windows:")
            for thr in THRESHOLDS:
                m = baseline[f"thr_{thr}"]
                print(
                    f"  thr={thr}: acc={m['accuracy']:.3f} P={m['precision']:.3f} "
                    f"R={m['recall']:.3f} F1={m['f1']:.3f} AUC={m['roc_auc']:.3f}"
                )

    # Natural-video sanity: fit on all labelled, score natural per participant.
    if len(labelled) < 2 or labelled["y"].nunique() < 2:
        raise SystemExit("Not enough labelled data to fit final model")

    final_pipe = _fit_pipe(
        labelled[FEAT_COLS].to_numpy(dtype=np.float64),
        labelled["y"].to_numpy(dtype=int),
    )
    natural_report: Dict[str, Dict] = {}
    if len(natural):
        for p, g in natural.groupby("participant"):
            proba_n = _proba(final_pipe, g[FEAT_COLS].to_numpy(dtype=np.float64))
            natural_report[p] = {
                "n": int(len(g)),
                "mean_prob": float(proba_n.mean()),
                "distracted_rate_0.5": float((proba_n >= 0.5).mean()),
                "distracted_rate_0.75": float((proba_n >= 0.75).mean()),
            }
        print("\n[natural] distracted rates @0.75:")
        for p, r in sorted(natural_report.items()):
            print(
                f"  {p}: n={r['n']} mean_p={r['mean_prob']:.3f} "
                f"rate@0.75={r['distracted_rate_0.75']:.3f}"
            )

    # Backup weak-label pack, then save final.
    STAGE.mkdir(parents=True, exist_ok=True)
    if old_path.exists():
        backup = STAGE / "model_v1_weaklabel.pkl"
        if not backup.exists():
            old_path.replace(backup)
            print(f"[save] backed up weak-label pack → {backup}")
        else:
            # Keep existing backup; overwrite current model.pkl below.
            print(f"[save] backup already present: {backup}")

    payload = {
        "model": final_pipe,
        "features": list(FEAT_COLS),
        "threshold": 0.75,
        "kind": "model5",
        "version": "participants_loso_v1",
        "loso_metrics": {
            "pooled": pooled,
            "folds": fold_rows,
            "baseline_weaklabel": baseline,
            "natural": natural_report,
            "n_labelled": int(len(labelled)),
            "n_natural": int(len(natural)),
            "participants": participants,
            "label_policy": "video_stem: distracted=1, focused/forced=0; natural=eval_only",
        },
    }
    out_model = STAGE / "model.pkl"
    joblib.dump(payload, out_model)
    print(f"[save] final M4 → {out_model}")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    metrics_path = LOG_DIR / "loso_metrics.json"
    metrics_path.write_text(json.dumps(payload["loso_metrics"], indent=2), encoding="utf-8")
    print(f"[save] metrics → {metrics_path}")


if __name__ == "__main__":
    main()
