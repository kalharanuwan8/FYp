# model4_engagement Training loop
from __future__ import annotations
from pathlib import Path
import argparse
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
import json
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

FEATURE_COLS = [
    "pose_ratio",
    "lw_speed_mean","lw_speed_std",
    "rw_speed_mean","rw_speed_std",
    "lw_to_nose_mean","rw_to_nose_mean",
    "lw_to_sh_mean","rw_to_sh_mean",
    "nose_jitter",
    "lw_below_sh_ratio","rw_below_sh_ratio",
]

def run(labeled_csv: Path, out_model: Path):
    df = pd.read_csv(labeled_csv)

    df = df.dropna(subset=["active_work"])
    X = df[FEATURE_COLS].fillna(0.0).to_numpy().astype(np.float32)
    y = df["active_work"].to_numpy().astype(int)

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=200, class_weight="balanced")),
    ])

    pipe.fit(Xtr, ytr)
    pred = pipe.predict(Xte)
    report_dict = classification_report(yte, pred, digits=4, output_dict=True)
    report_str = classification_report(yte, pred, digits=4)
    print("\n--- Engagement Model Evaluation Report ---")
    print(report_str)

    cm = confusion_matrix(yte, pred).tolist()
    acc = float(accuracy_score(yte, pred))

    metrics = {
        "accuracy": acc,
        "classification_report": report_dict,
        "confusion_matrix": cm,
        "test_samples": len(yte),
    }

    # Save metrics JSON for documentation/thesis
    metrics_dir = Path("outputs/logs/model4_engagement")
    metrics_dir.mkdir(parents=True, exist_ok=True)
    with open(metrics_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"Saved evaluation metrics to: {metrics_dir / 'metrics.json'}")

    out_model.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": pipe,
        "feature_cols": FEATURE_COLS,
        "val_best": {
            "accuracy": acc,
            "f1": report_dict["macro avg"]["f1-score"],
            "precision": report_dict["macro avg"]["precision"],
            "recall": report_dict["macro avg"]["recall"],
            "binary_f1": report_dict["1"]["f1-score"] if "1" in report_dict else report_dict.get("1.0", {}).get("f1-score", 0),
        },
        "metrics": metrics
    }, out_model)
    print(f"Saved model package: {out_model}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/processed/model4_engagement/labeled.csv")
    ap.add_argument("--out", default="outputs/checkpoints/model4_engagement/model.pkl")
    args = ap.parse_args()
    run(Path(args.data), Path(args.out))
