# model4_engagement Training loop
from __future__ import annotations
from pathlib import Path
import argparse
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
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

    print(classification_report(yte, pred, digits=4))

    out_model.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": pipe, "feature_cols": FEATURE_COLS}, out_model)
    print(f"Saved: {out_model}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/processed/model3_activity/labeled.csv")
    ap.add_argument("--out", default="outputs/checkpoints/model3_activity/model.pkl")
    args = ap.parse_args()
    run(Path(args.data), Path(args.out))
