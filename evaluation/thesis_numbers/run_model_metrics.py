"""
Thesis metric run for M1, M2, M4, M5, Haar-on-BIWI, and the natural-recording check.

Does not modify deployed checkpoints. Retrained M5 copies are written only under
evaluation/thesis_numbers/artifacts/.

Run from anywhere:
  venvpy312\\Scripts\\python.exe evaluation\\thesis_numbers\\run_model_metrics.py
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

SEED = 42

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
OUT = Path(__file__).resolve().parent
RAW = OUT / "raw"
ART = OUT / "artifacts"
RAW.mkdir(parents=True, exist_ok=True)
ART.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(MODELS))

import numpy as np

random.seed(SEED)
np.random.seed(SEED)


def sha256_file(path: Path) -> dict:
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
            n += len(chunk)
    return {"path": str(path), "sha256": h.hexdigest(), "bytes": n}


def dump(name: str, obj) -> None:
    path = RAW / name
    path.write_text(json.dumps(obj, indent=2, allow_nan=True), encoding="utf-8")
    print(f"WROTE {path}", flush=True)


def binary_pack(y_true, y_pred, y_score, positive_label: int = 1) -> dict:
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_recall_fscore_support,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    labels = [0, 1]
    prec_c, rec_c, f1_c, sup_c = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    out = {
        "n": int(y_true.shape[0]),
        "positive_label": positive_label,
        "class_counts_true": {
            "0": int(np.sum(y_true == 0)),
            "1": int(np.sum(y_true == 1)),
        },
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_positive": float(
            precision_score(y_true, y_pred, pos_label=positive_label, zero_division=0)
        ),
        "recall_positive": float(
            recall_score(y_true, y_pred, pos_label=positive_label, zero_division=0)
        ),
        "f1_positive": float(
            f1_score(y_true, y_pred, pos_label=positive_label, zero_division=0)
        ),
        "precision_macro": float(
            precision_score(y_true, y_pred, average="macro", zero_division=0)
        ),
        "recall_macro": float(
            recall_score(y_true, y_pred, average="macro", zero_division=0)
        ),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "per_class": {
            str(lab): {
                "precision": float(prec_c[i]),
                "recall": float(rec_c[i]),
                "f1": float(f1_c[i]),
                "support": int(sup_c[i]),
            }
            for i, lab in enumerate(labels)
        },
        "confusion_matrix_labels": labels,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }
    if y_score is None:
        out["roc_auc"] = None
        out["roc_auc_note"] = "no score"
    else:
        score = np.asarray(y_score, dtype=np.float64)
        if len(np.unique(y_true)) < 2:
            out["roc_auc"] = None
            out["roc_auc_note"] = "only one class in y_true"
        else:
            out["roc_auc"] = float(roc_auc_score(y_true, score))
            out["roc_auc_note"] = "sklearn.roc_auc_score on the provided score for class 1"
    return out


def blocked_indices(n: int, purge: int = 2) -> dict:
    """
    Contiguous 70/15/15 by floor, then drop exactly 2 windows at each boundary
    (the index immediately before the cut and the index at the cut).
    """
    c1 = int(np.floor(n * 0.70))
    c2 = int(np.floor(n * 0.85))
    train = list(range(0, max(0, c1 - 1)))
    val = list(range(c1 + 1, max(c1 + 1, c2 - 1)))
    test = list(range(c2 + 1, n))
    dropped = []
    if n > 0:
        for idx in (c1 - 1, c1, c2 - 1, c2):
            if 0 <= idx < n:
                dropped.append(idx)
    return {
        "n": n,
        "c1": c1,
        "c2": c2,
        "train": train,
        "val": val,
        "test": test,
        "dropped": sorted(set(dropped)),
        "rule": (
            "Sort by window_start_sec. "
            "c1=floor(0.70*n), c2=floor(0.85*n). "
            "train=[0, c1-1), val=[c1+1, c2-1), test=[c2+1, n). "
            "Dropped indices are c1-1, c1, c2-1, c2 when in range "
            "(2 windows at the train|val boundary and 2 at the val|test boundary)."
        ),
    }


def main() -> None:
    import joblib
    import pandas as pd
    import torch
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    # Dataset CSVs use paths relative to models/
    import os

    os.chdir(MODELS)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    meta = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "device": device,
        "cuda_device_name": (
            torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
        ),
        "torch": torch.__version__,
        "cwd": str(Path.cwd()),
        "cudnn_deterministic": True,
    }
    print("META", json.dumps(meta), flush=True)

    ckpt_paths = {
        "m1_best": MODELS / "outputs/checkpoints/model1_gaze/best.pt",
        "m1_last": MODELS / "outputs/checkpoints/model1_gaze/last.pt",
        "m1_epoch15_backup": MODELS
        / "outputs/checkpoints/model1_gaze/last_epoch15_96_backup.pt",
        "m2_best": MODELS / "outputs/checkpoints/model2_pose/best.pt",
        "m2_last": MODELS / "outputs/checkpoints/model2_pose/last.pt",
        "m4": MODELS / "outputs/checkpoints/model4_engagement/model.pkl",
        "m5": MODELS / "outputs/checkpoints/model5_fusion/model.pkl",
    }
    hashes = {k: sha256_file(p) for k, p in ckpt_paths.items()}
    dump("checkpoint_hashes.json", hashes)

    # ------------------------------------------------------------------ M1
    print("M1 start", flush=True)
    from torch.utils.data import DataLoader
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_recall_fscore_support,
    )
    from src.model1_gaze.dataset import LABEL4, MPIIGaze4Class
    from src.model1_gaze.model import build_model

    m1_path = ckpt_paths["m1_best"]
    ckpt = torch.load(m1_path, map_location=device, weights_only=False)
    m1_meta = {
        "loaded_path": str(m1_path),
        "sha256": hashes["m1_best"]["sha256"],
        "epoch_field": ckpt.get("epoch"),
        "img_size_field": ckpt.get("img_size"),
        "best_f1_field": ckpt.get("best_f1"),
        "num_classes": ckpt.get("num_classes"),
        "keys": sorted(ckpt.keys()),
        "identical_sha_to_last": hashes["m1_best"]["sha256"] == hashes["m1_last"]["sha256"],
        "identical_sha_to_epoch15_backup": hashes["m1_best"]["sha256"]
        == hashes["m1_epoch15_backup"]["sha256"],
    }
    log_path = MODELS / "outputs/logs/model1_gaze/train_log.csv"
    log_rows = []
    if log_path.exists():
        log_df = pd.read_csv(log_path)
        log_rows = log_df.to_dict(orient="records")
        # exact max: if ties, report all
        f1col = log_df["val_f1"].astype(float)
        max_f1 = float(f1col.max())
        best_epochs = log_df.loc[f1col == max_f1, "epoch"].tolist()
        m1_meta["train_log_path"] = str(log_path)
        m1_meta["train_log_rows"] = log_rows
        m1_meta["train_log_max_val_f1"] = max_f1
        m1_meta["train_log_epochs_at_max_val_f1"] = [int(x) for x in best_epochs]
    else:
        m1_meta["train_log_path"] = None

    img_size = int(ckpt.get("img_size", 96))
    names = [k for k, v in sorted(LABEL4.items(), key=lambda kv: kv[1])]

    def eval_gaze(csv_path: Path, split_name: str) -> dict:
        ds = MPIIGaze4Class(csv_path, img_size=img_size, train=False)
        subjects = sorted(ds.df["subject_id"].astype(str).unique().tolist())
        loader = DataLoader(
            ds, batch_size=256, shuffle=False, num_workers=0, pin_memory=False
        )
        model = build_model(num_classes=int(ckpt["num_classes"]), pretrained=False).to(device)
        model.load_state_dict(ckpt["model_state"])
        model.eval()
        y_true, y_pred = [], []
        with torch.no_grad():
            for i, (x, y) in enumerate(loader):
                x = x.to(device)
                pred = torch.argmax(model(x), dim=1).cpu().numpy()
                y_pred.append(pred)
                y_true.append(y.numpy())
                if (i + 1) % 10 == 0:
                    print(f"  {split_name} batch {i+1}", flush=True)
        y_true = np.concatenate(y_true)
        y_pred = np.concatenate(y_pred)
        prec, rec, f1s, sup = precision_recall_fscore_support(
            y_true, y_pred, labels=[0, 1, 2, 3], zero_division=0
        )
        return {
            "split": split_name,
            "csv": str(csv_path),
            "n": int(len(ds)),
            "n_predicted": int(y_true.shape[0]),
            "subjects": subjects,
            "image_cache_used": ds.images is not None,
            "img_size": img_size,
            "label_order": names,
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
            "per_class": {
                names[i]: {
                    "precision": float(prec[i]),
                    "recall": float(rec[i]),
                    "f1": float(f1s[i]),
                    "support": int(sup[i]),
                }
                for i in range(4)
            },
            "confusion_matrix_rows_true_cols_pred": confusion_matrix(
                y_true, y_pred, labels=[0, 1, 2, 3]
            ).tolist(),
        }

    m1 = {
        "checkpoint": m1_meta,
        "test": eval_gaze(MODELS / "data/processed/model1_gaze/test.csv", "test"),
        "val": eval_gaze(MODELS / "data/processed/model1_gaze/val.csv", "val"),
    }
    dump("m1_gaze.json", m1)
    print("M1 done", m1["test"]["n"], m1["test"]["accuracy"], flush=True)
    del ckpt

    # ------------------------------------------------------------------ M2
    print("M2 start", flush=True)
    import torch.nn as nn
    from PIL import Image
    from torchvision import models, transforms

    pose_tf = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )
    pose_ckpt = torch.load(ckpt_paths["m2_best"], map_location=device, weights_only=False)
    pose_model = models.resnet18(weights=None)
    pose_model.fc = nn.Linear(pose_model.fc.in_features, 3)
    state = {k.replace("net.", ""): v for k, v in pose_ckpt["model"].items()}
    pose_model.load_state_dict(state)
    pose_model.to(device).eval()

    def eval_pose(csv_path: Path, split_name: str) -> dict:
        df = pd.read_csv(csv_path)
        subjects = sorted(df["subject_id"].astype(str).unique().tolist())
        abs_err = np.zeros(3, dtype=np.float64)
        n_ok = 0
        missing = []
        batch_x = []
        batch_y = []

        def flush_batch():
            nonlocal abs_err, n_ok, batch_x, batch_y
            if not batch_x:
                return
            x = torch.stack(batch_x, dim=0).to(device)
            y = np.stack(batch_y, axis=0)
            with torch.no_grad():
                p = pose_model(x).cpu().numpy()
            abs_err += np.abs(p - y).sum(axis=0)
            n_ok += y.shape[0]
            batch_x = []
            batch_y = []

        for i, row in df.iterrows():
            img_path = Path(row["img_path"])
            if not img_path.is_file():
                missing.append(str(img_path))
                continue
            img = Image.open(img_path).convert("RGB")
            batch_x.append(pose_tf(img))
            batch_y.append(
                np.array(
                    [row["yaw_deg"], row["pitch_deg"], row["roll_deg"]],
                    dtype=np.float64,
                )
            )
            if len(batch_x) == 64:
                flush_batch()
                if n_ok % 640 == 0:
                    print(f"  {split_name} n={n_ok}", flush=True)
        flush_batch()
        mae = (abs_err / n_ok).tolist() if n_ok else None
        mean_mae = float(np.mean(abs_err / n_ok)) if n_ok else None
        return {
            "split": split_name,
            "csv": str(csv_path),
            "n_rows": int(len(df)),
            "n_scored": int(n_ok),
            "n_missing_images": len(missing),
            "missing_images_head": missing[:5],
            "subjects": subjects,
            "mae_yaw_deg": None if mae is None else float(mae[0]),
            "mae_pitch_deg": None if mae is None else float(mae[1]),
            "mae_roll_deg": None if mae is None else float(mae[2]),
            "mae_mean_deg": mean_mae,
            "mae_definition": "mean over scored frames of |pred-target| in degrees; mean is the unweighted mean of the three MAEs",
        }

    pose_log_candidates = list((MODELS / "outputs").rglob("*"))
    pose_logs = [
        str(p)
        for p in pose_log_candidates
        if p.is_file() and "pose" in p.name.lower() and p.suffix.lower() in {".csv", ".txt", ".log", ".json"}
    ]
    m2 = {
        "checkpoint": {
            "loaded_path": str(ckpt_paths["m2_best"]),
            "sha256": hashes["m2_best"]["sha256"],
            "epoch_field": pose_ckpt.get("epoch"),
            "best_val_field": pose_ckpt.get("best_val"),
            "keys": sorted([k for k in pose_ckpt.keys()]),
        },
        "pose_log_files_under_models_outputs": pose_logs,
        "test": eval_pose(MODELS / "data/processed/model2_pose/test.csv", "test"),
        "val": eval_pose(MODELS / "data/processed/model2_pose/val.csv", "val"),
    }
    dump("m2_pose.json", m2)
    print("M2 done", flush=True)
    del pose_model, pose_ckpt
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # ------------------------------------------------------------------ M4
    print("M4 start", flush=True)
    from sklearn.model_selection import train_test_split

    m4_pack = joblib.load(ckpt_paths["m4"])
    labeled = pd.read_csv(MODELS / "data/processed/model4_engagement/labeled.csv")
    labeled = labeled.dropna(subset=["active_work"])
    cols = m4_pack["feature_cols"]
    X = labeled[cols].fillna(0.0).to_numpy().astype(np.float32)
    y = labeled["active_work"].to_numpy().astype(int)
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    model4 = m4_pack["model"]
    pred4 = model4.predict(Xte)
    proba4 = model4.predict_proba(Xte)[:, 1]
    m4 = {
        "checkpoint_sha256": hashes["m4"]["sha256"],
        "feature_cols": list(cols),
        "n_labeled_rows": int(len(labeled)),
        "split": "train_test_split test_size=0.25 random_state=42 stratify=y (same call as models/src/model4_engagement/train.py). Model weights were not refit.",
        "n_test": int(len(yte)),
        "metrics": binary_pack(yte, pred4, proba4, positive_label=1),
        "positive_class_meaning": "active_work=1 as stored in labeled.csv. Labels were produced by models/src/model4_engagement/labelweak.py heuristic rules, so these scores are agreement with those rules.",
        "pickle_keys": sorted(m4_pack.keys()) if isinstance(m4_pack, dict) else None,
    }
    dump("m4_engagement.json", m4)
    print("M4 done", m4["n_test"], flush=True)

    # ------------------------------------------------------------------ M5
    print("M5 start", flush=True)
    m5_pack = joblib.load(ckpt_paths["m5"])
    feats = list(m5_pack["features"])
    threshold = float(m5_pack.get("threshold", 0.5))
    fusion = m5_pack["model"]

    def score_m5(df: pd.DataFrame, model, feature_names, thr: float) -> dict:
        X = df[feature_names].fillna(0.0).to_numpy().astype(np.float32)
        y = df["y"].to_numpy().astype(int)
        proba = model.predict_proba(X)[:, 1]
        pred = (proba >= thr).astype(int)
        packed = binary_pack(y, pred, proba, positive_label=1)
        packed["threshold"] = thr
        packed["decision"] = "DISTRACTED if predict_proba class 1 >= threshold else FOCUSED (y=1 is distracted)"
        return packed

    test_df = pd.read_csv(MODELS / "data/processed/model5_fusion/test.csv")
    train_df = pd.read_csv(MODELS / "data/processed/model5_fusion/train.csv")
    val_df = pd.read_csv(MODELS / "data/processed/model5_fusion/val.csv")
    m5_existing = score_m5(test_df, fusion, feats, threshold)

    all_df = pd.concat([train_df, val_df, test_df], ignore_index=True)
    pieces = []
    split_audit = []
    for vid, g in all_df.groupby("video_id", sort=True):
        g = g.sort_values(["window_start_sec", "y"]).reset_index(drop=True)
        spec = blocked_indices(len(g), purge=2)
        split_audit.append(
            {
                "video_id": str(vid),
                "n": spec["n"],
                "c1": spec["c1"],
                "c2": spec["c2"],
                "n_train": len(spec["train"]),
                "n_val": len(spec["val"]),
                "n_test": len(spec["test"]),
                "dropped_window_start_sec": [
                    float(g.loc[i, "window_start_sec"]) for i in spec["dropped"]
                ],
                "rule": spec["rule"],
            }
        )
        for name, idxs in (
            ("train", spec["train"]),
            ("val", spec["val"]),
            ("test", spec["test"]),
        ):
            if not idxs:
                continue
            part = g.iloc[idxs].copy()
            part["blocked_split"] = name
            pieces.append(part)
    blocked = pd.concat(pieces, ignore_index=True) if pieces else all_df.iloc[0:0].copy()
    b_train = blocked[blocked["blocked_split"] == "train"]
    b_val = blocked[blocked["blocked_split"] == "val"]
    b_test = blocked[blocked["blocked_split"] == "test"]

    def fit_lr(df_tr: pd.DataFrame, feature_names):
        pipe = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "lr",
                    LogisticRegression(
                        max_iter=2000,
                        C=1.0,
                        solver="lbfgs",
                        random_state=SEED,
                    ),
                ),
            ]
        )
        Xtr = df_tr[feature_names].fillna(0.0).to_numpy().astype(np.float32)
        ytr = df_tr["y"].to_numpy().astype(int)
        pipe.fit(Xtr, ytr)
        return pipe

    blocked_model = fit_lr(b_train, feats)
    joblib.dump(
        {
            "model": blocked_model,
            "features": feats,
            "threshold": 0.5,
            "seed": SEED,
            "note": "copy for blocked temporal split; not the deployed checkpoint",
        },
        ART / "m5_blocked_all9.joblib",
    )
    m5_blocked = score_m5(b_test, blocked_model, feats, 0.5)

    def rule_pred(df: pd.DataFrame) -> np.ndarray:
        g = df["gaze_away_ratio"].to_numpy(dtype=np.float64)
        yaw = np.abs(df["yaw_mean"].to_numpy(dtype=np.float64))
        pitch = np.abs(df["pitch_mean"].to_numpy(dtype=np.float64))
        return ((g > 0.20) | (yaw > 10) | (pitch > 10)).astype(int)

    def score_rule(df: pd.DataFrame) -> dict:
        y = df["y"].to_numpy().astype(int)
        pred = rule_pred(df)
        packed = binary_pack(y, pred, pred.astype(np.float64), positive_label=1)
        packed["score_note"] = (
            "Hard rule. ROC-AUC uses the 0/1 rule output as the score, not a probability."
        )
        packed["rule"] = "distracted if gaze_away_ratio > 0.20 or abs(yaw_mean) > 10 or abs(pitch_mean) > 10"
        return packed

    ablations = {}
    for name, k in (("gaze_1_to_5", 5), ("gaze_head_1_to_8", 8), ("all_9", 9)):
        use = feats[:k]
        model_k = fit_lr(b_train, use)
        joblib.dump(
            {"model": model_k, "features": use, "seed": SEED},
            ART / f"m5_blocked_{name}.joblib",
        )
        ablations[name] = {
            "features": use,
            "metrics": score_m5(b_test, model_k, use, 0.5),
        }

    m5 = {
        "checkpoint_sha256": hashes["m5"]["sha256"],
        "deployed_features": feats,
        "deployed_threshold": threshold,
        "deployed_threshold_tuning": m5_pack.get("threshold_tuning"),
        "deployed_class_weight": m5_pack.get("class_weight"),
        "deployed_C": m5_pack.get("C"),
        "deployed_max_iter": m5_pack.get("max_iter"),
        "existing_test_split": {
            "csv": str(MODELS / "data/processed/model5_fusion/test.csv"),
            "n_file_rows": int(len(test_df)),
            "video_counts": test_df["video_id"].value_counts().to_dict(),
            "metrics": m5_existing,
        },
        "blocked_split": {
            "source": "concat of existing train.csv+val.csv+test.csv (ambiguous windows already removed by prep.py), grouped by video_id, sorted by window_start_sec",
            "seed": SEED,
            "pipeline": "StandardScaler + LogisticRegression(C=1.0, solver=lbfgs, max_iter=2000, random_state=42). Deployed train.py does not pass random_state; lbfgs is deterministic for a fixed matrix. Copy saved under evaluation/thesis_numbers/artifacts/. Deployed model.pkl was not overwritten.",
            "per_video": split_audit,
            "n_train": int(len(b_train)),
            "n_val": int(len(b_val)),
            "n_test": int(len(b_test)),
            "metrics_test": m5_blocked,
        },
        "rule_baseline_existing_test": score_rule(test_df),
        "rule_baseline_blocked_test": score_rule(b_test),
        "ablation_blocked_test": ablations,
    }
    # value_counts keys may be non-str
    m5["existing_test_split"]["video_counts"] = {
        str(k): int(v) for k, v in test_df["video_id"].value_counts().to_dict().items()
    }
    dump("m5_fusion.json", m5)
    print("M5 done", flush=True)

    # ------------------------------------------------------------------ Haar
    print("HAAR start", flush=True)
    import cv2

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    pose_test = pd.read_csv(MODELS / "data/processed/model2_pose/test.csv")
    bins = [
        ("0-15", 0.0, 15.0),
        ("15-30", 15.0, 30.0),
        ("30-45", 30.0, 45.0),
        ("45-60", 45.0, 60.0),
        (">60", 60.0, None),
    ]
    bin_found = {b[0]: 0 for b in bins}
    bin_n = {b[0]: 0 for b in bins}
    unreadable = 0
    for _, row in pose_test.iterrows():
        ay = abs(float(row["yaw_deg"]))
        name = None
        for label, lo, hi in bins:
            if hi is None:
                if ay >= lo:
                    name = label
            elif lo <= ay < hi:
                name = label
        if name is None:
            continue
        img = cv2.imread(str(row["img_path"]))
        if img is None:
            unreadable += 1
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(50, 50))
        bin_n[name] += 1
        if len(faces) > 0:
            bin_found[name] += 1
    haar_rows = []
    for label, _, _ in bins:
        n = bin_n[label]
        fnd = bin_found[label]
        haar_rows.append(
            {
                "abs_yaw_bin": label,
                "bin_rule": "lower inclusive, upper exclusive; >60 is abs(yaw) >= 60",
                "n_readable": n,
                "n_face_found": fnd,
                "ratio_face_found": (None if n == 0 else float(fnd) / float(n)),
            }
        )
    haar = {
        "cascade": cascade_path,
        "call": "detectMultiScale(gray, 1.1, 5, minSize=(50, 50)) matching ml_service.detect_face_crop / detect_eye_crop",
        "frames": "models/data/processed/model2_pose/test.csv (BIWI subjects in that file)",
        "subjects": sorted(pose_test["subject_id"].astype(str).unique().tolist()),
        "n_csv_rows": int(len(pose_test)),
        "n_unreadable": unreadable,
        "bins": haar_rows,
    }
    dump("haar_biwi_test.json", haar)
    print("HAAR done", flush=True)

    # ------------------------------------------------------------------ natural
    print("NATURAL start", flush=True)
    gaze_n = pd.read_csv(MODELS / "data/processed/model1_gaze/window_preds_natural.csv")
    pose_n = pd.read_csv(MODELS / "data/processed/model2_pose/window_pose_natural.csv")
    eng_n = pd.read_csv(MODELS / "data/processed/model4_engagement/preds_natural.csv")
    for frame in (gaze_n, pose_n, eng_n):
        frame["window_start_sec"] = frame["window_start_sec"].round(0).astype(int)
    gaze_n = gaze_n.groupby(["video_id", "window_start_sec"], as_index=False).first()
    pose_n = pose_n.groupby(["video_id", "window_start_sec"], as_index=False).first()
    eng_n = eng_n.groupby(["video_id", "window_start_sec"], as_index=False).first()
    if "engagement_prob_mean" not in eng_n.columns and "active_work_prob" in eng_n.columns:
        eng_n = eng_n.rename(columns={"active_work_prob": "engagement_prob_mean"})
    nat = gaze_n.merge(pose_n, on=["video_id", "window_start_sec"], how="inner")
    nat = nat.merge(eng_n, on=["video_id", "window_start_sec"], how="inner")
    nat["p_center_mean"] = nat["p_center"]
    nat["p_left_mean"] = nat["p_left"]
    nat["p_right_mean"] = nat["p_right"]
    nat["p_down_mean"] = nat["p_down"]
    s = nat["p_center_mean"] + nat["p_left_mean"] + nat["p_right_mean"] + nat["p_down_mean"] + 1e-8
    nat["gaze_away_ratio"] = (nat["p_left_mean"] + nat["p_right_mean"] + nat["p_down_mean"]) / s
    argmax_from_probs = nat[["p_center", "p_left", "p_right", "p_down"]].to_numpy().argmax(axis=1)
    inv = {0: "center", 1: "left", 2: "right", 3: "down"}
    argmax_names = [inv[int(i)] for i in argmax_from_probs]
    Xn = nat.reindex(columns=feats).fillna(0.0).to_numpy().astype(np.float32)
    proba_n = fusion.predict_proba(Xn)[:, 1]
    pred_n = (proba_n >= threshold).astype(int)

    def file_stamp(p: Path) -> dict:
        st = p.stat()
        return {"path": str(p), "bytes": st.st_size, "mtime_epoch": st.st_mtime}

    natural = {
        "note": (
            "Computed from the stored natural-recording window CSVs joined the same way as "
            "models/src/model5_fusion/prep.py. This is not a fresh forward pass of the epoch-15 "
            "gaze checkpoint. File mtimes are included so the gaze CSV can be compared with the checkpoint."
        ),
        "files": {
            "gaze": file_stamp(MODELS / "data/processed/model1_gaze/window_preds_natural.csv"),
            "pose": file_stamp(MODELS / "data/processed/model2_pose/window_pose_natural.csv"),
            "engagement": file_stamp(MODELS / "data/processed/model4_engagement/preds_natural.csv"),
            "m1_checkpoint": file_stamp(ckpt_paths["m1_best"]),
            "m5_checkpoint": file_stamp(ckpt_paths["m5"]),
        },
        "n_windows_joined": int(len(nat)),
        "video_ids": sorted(nat["video_id"].astype(str).unique().tolist()),
        "m1_pred_name_counts": {str(k): int(v) for k, v in gaze_n["pred_name"].value_counts().to_dict().items()},
        "m1_argmax_of_stored_probabilities_counts": {
            k: int(argmax_names.count(k)) for k in ("center", "left", "right", "down")
        },
        "pred_name_matches_argmax": bool(
            list(gaze_n["pred_name"].astype(str)) == argmax_names
            if len(gaze_n) == len(nat)
            else False
        ),
        "mean_p_center": float(nat["p_center"].mean()),
        "m5_threshold": threshold,
        "n_m5_distracted": int(pred_n.sum()),
        "ratio_m5_distracted": float(pred_n.mean()) if len(pred_n) else None,
    }
    # pred_name is on gaze_n; after groupby order should match nat if merge is inner and gaze is left base
    # Recompute match on nat if pred_name survived the merge
    if "pred_name" in nat.columns:
        natural["m1_pred_name_counts"] = {
            str(k): int(v) for k, v in nat["pred_name"].value_counts().to_dict().items()
        }
        natural["pred_name_matches_argmax"] = bool(
            nat["pred_name"].astype(str).tolist() == argmax_names
        )
    dump("natural_recording.json", natural)
    print("NATURAL done", flush=True)

    meta["finished_utc"] = datetime.now(timezone.utc).isoformat()
    dump("run_meta.json", meta)
    print("ALL_MODEL_METRICS_DONE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        err = traceback.format_exc()
        (RAW / "run_model_metrics_error.txt").write_text(err, encoding="utf-8")
        print(err, flush=True)
        raise
