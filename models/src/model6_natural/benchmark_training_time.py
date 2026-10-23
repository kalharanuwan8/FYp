"""Training-time benchmark for Plan 1 (fit() time only).

Scope -- read this before quoting any number from this script:

  * It times ONLY ``model.fit()`` (wall clock, ``time.perf_counter``).
  * It does NOT time recording, labelling, MediaPipe feature extraction,
    CSV loading, prediction/scoring, or model saving. Those are reported
    separately (``eval_seconds``) or not at all.
  * If no real window-feature CSV is given, it generates a *synthetic*
    table at the scale Plan 1 describes (N subjects x ~20 min, 1 s hop,
    ~20 numeric features). Synthetic rows exist only to size the training
    job; any F1 printed for them is a sanity check, NOT a result.

Real data, when it exists:

    venvpy312\\Scripts\\python.exe -m models.src.model6_natural.benchmark_training_time \
        --csv models/data/model6_natural/windows.csv \
        --subject-col subject_id --label-col y

Synthetic scale check (default, Plan 1 scale):

    venvpy312\\Scripts\\python.exe -m models.src.model6_natural.benchmark_training_time

Output: models/reports/model6_natural/training_time.json
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------- features
# ~20 window features named after Plan 1, Step 4.
FEATURES: list[str] = [
    "gaze_dev_mean", "gaze_dev_std", "head_yaw_dev", "head_pitch_dev",
    "on_screen_ratio", "off_screen_dwell_sec", "glance_count",
    "blink_rate", "perclos", "face_present_ratio",
    "body_motion_energy", "hand_to_face_ratio", "talking_score",
    "tab_hidden_ratio", "idle_sec", "video_playing_ratio", "mouse_activity",
    "calibrated_gaze_dev", "calibrated_head_dev", "calibration_residual",
]
CALIBRATION_FEATURES = ["calibrated_gaze_dev", "calibrated_head_dev", "calibration_residual"]
INTERACTION_FEATURES = ["tab_hidden_ratio", "idle_sec", "video_playing_ratio", "mouse_activity"]

ABLATIONS: dict[str, list[str]] = {
    "full": FEATURES,
    "no_calibration": [f for f in FEATURES if f not in CALIBRATION_FEATURES],
    "no_interaction": [f for f in FEATURES if f not in INTERACTION_FEATURES],
}


# ------------------------------------------------------------------- data
def make_synthetic_window_table(
    n_subjects: int, minutes_per_subject: int, window_sec: int, seed: int = 42
) -> pd.DataFrame:
    """One row per 1 s hop. Labels drive the features so fit() does real work."""
    rng = np.random.default_rng(seed + window_sec)
    rows_per_subject = max(1, minutes_per_subject * 60 - window_sec + 1)
    frames = []
    for subject in range(n_subjects):
        # Random distracted episodes per subject (timing proxy only).
        y = np.zeros(rows_per_subject, dtype=int)
        t = 0
        episode = False
        while t < rows_per_subject:
            episode = not episode  # alternate, so every subject has both classes
            length = int(rng.integers(5, 60)) if episode else int(rng.integers(20, 120))
            y[t : t + length] = 1 if episode else 0
            t += length
        signal = y.astype(float) + rng.normal(0, 0.35, rows_per_subject)
        data = {f: rng.normal(0, 1, rows_per_subject) + 0.6 * signal for f in FEATURES}
        # Ratios stay in [0, 1]-ish territory; exact realism is irrelevant for timing.
        for col in ("on_screen_ratio", "face_present_ratio"):
            data[col] = np.clip(0.8 - 0.5 * signal + rng.normal(0, 0.1, rows_per_subject), 0, 1)
        frame = pd.DataFrame(data)
        frame["subject_id"] = f"s{subject + 1:02d}"
        frame["y"] = y
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def load_real_table(csv_path: Path, subject_col: str, label_col: str,
                    feature_cols: list[str] | None) -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(csv_path)
    if subject_col not in df.columns or label_col not in df.columns:
        raise ValueError(f"CSV must contain '{subject_col}' and '{label_col}' columns")
    feats = feature_cols or [c for c in df.columns if c not in (subject_col, label_col)]
    if not feats:
        raise ValueError("No feature columns found in CSV")
    df = df.rename(columns={subject_col: "subject_id", label_col: "y"})
    return df[["subject_id", "y", *feats]], feats


# ----------------------------------------------------------------- models
def build_model(kind: str):
    if kind == "logreg":
        return Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000)),
        ])
    if kind == "lightgbm":
        try:
            from lightgbm import LGBMClassifier
        except ImportError:
            print("[warn] lightgbm not installed in this venv; "
                  "falling back to sklearn HistGradientBoostingClassifier")
            return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05)
        return LGBMClassifier(
            n_estimators=300, learning_rate=0.05, num_leaves=31,
            n_jobs=-1, verbose=-1,
        )
    raise ValueError(f"Unknown model kind: {kind}")


# -------------------------------------------------------------- LOSO loop
def run_loso(df: pd.DataFrame, features: list[str], model_kind: str) -> dict:
    """Leave-one-subject-out. Only fit() is timed; scoring is kept separate."""
    subjects = sorted(df["subject_id"].unique())
    fit_seconds: list[float] = []
    f1s: list[float] = []
    eval_seconds = 0.0
    for held_out in subjects:
        train = df[df["subject_id"] != held_out]
        test = df[df["subject_id"] == held_out]
        if train["y"].nunique() < 2 or len(test) == 0:
            continue
        model = build_model(model_kind)
        start = time.perf_counter()
        model.fit(train[features].to_numpy(dtype=np.float64), train["y"].to_numpy(dtype=int))
        fit_seconds.append(time.perf_counter() - start)  # <-- the only timed part

        start = time.perf_counter()
        pred = model.predict(test[features].to_numpy(dtype=np.float64))
        eval_seconds += time.perf_counter() - start
        if test["y"].nunique() == 2:
            f1s.append(float(f1_score(test["y"], pred, average="macro")))

    total_fit = float(sum(fit_seconds))
    return {
        "folds": len(fit_seconds),
        "rows_total": int(len(df)),
        "n_features": len(features),
        "fit_seconds_total": round(total_fit, 3),
        "fit_seconds_mean_per_fold": round(statistics.mean(fit_seconds), 3) if fit_seconds else None,
        "fit_seconds_median_per_fold": round(statistics.median(fit_seconds), 3) if fit_seconds else None,
        "eval_seconds_total_not_training": round(float(eval_seconds), 3),
        "macro_f1_mean_sanity_only": round(float(np.mean(f1s)), 4) if f1s else None,
    }


# ------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Plan 1 training-time benchmark (fit() only)")
    ap.add_argument("--csv", type=Path, default=None, help="Real window-feature CSV (else synthetic)")
    ap.add_argument("--subject-col", default="subject_id")
    ap.add_argument("--label-col", default="y")
    ap.add_argument("--subjects", type=int, default=15, help="Synthetic: participant count")
    ap.add_argument("--minutes", type=int, default=20, help="Synthetic: minutes per participant")
    ap.add_argument("--windows", default="2,5,10", help="Synthetic: window sizes in seconds")
    ap.add_argument("--models", default="logreg,lightgbm")
    ap.add_argument("--no-ablations", action="store_true", help="Skip no-calibration/no-interaction runs")
    ap.add_argument("--out", type=Path,
                    default=Path("models/reports/model6_natural/training_time.json"))
    args = ap.parse_args()

    model_kinds = [m.strip() for m in args.models.split(",") if m.strip()]
    results: dict = {
        "scope": "fit() wall-clock time only; excludes recording, labelling, "
                 "feature extraction, CSV loading, prediction and saving",
        "data_source": "real_csv" if args.csv else "synthetic_timing_proxy_not_a_result",
        "environment": {
            "python": sys.version.split()[0],
            "executable": sys.executable,
            "platform": platform.platform(),
        },
        "runs": [],
    }

    if args.csv:
        df, feats = load_real_table(args.csv, args.subject_col, args.label_col, None)
        print(f"Real CSV: {len(df):,} rows, {len(feats)} features, "
              f"{df['subject_id'].nunique()} subjects")
        for kind in model_kinds:
            run = {"config": f"csv / {kind} / full", **run_loso(df, feats, kind)}
            results["runs"].append(run)
            print(f"  {run['config']}: fit total {run['fit_seconds_total']}s "
                  f"over {run['folds']} folds")
    else:
        for window in [int(w) for w in args.windows.split(",") if w.strip()]:
            df = make_synthetic_window_table(args.subjects, args.minutes, window)
            print(f"Synthetic window={window}s: {len(df):,} rows, "
                  f"{len(FEATURES)} features, {args.subjects} subjects")
            for kind in model_kinds:
                run = {"config": f"window{window}s / {kind} / full",
                       **run_loso(df, FEATURES, kind)}
                results["runs"].append(run)
                print(f"  {run['config']}: fit total {run['fit_seconds_total']}s "
                      f"over {run['folds']} folds")
            if not args.no_ablations:
                # Ablations only for the main model (last / lightgbm if present).
                main_kind = "lightgbm" if "lightgbm" in model_kinds else model_kinds[-1]
                for name, feats in ABLATIONS.items():
                    if name == "full":
                        continue
                    run = {"config": f"window{window}s / {main_kind} / {name}",
                           **run_loso(df, feats, main_kind)}
                    results["runs"].append(run)
                    print(f"  {run['config']}: fit total {run['fit_seconds_total']}s "
                          f"over {run['folds']} folds")

    if results["runs"]:
        results["fit_seconds_grand_total"] = round(
            sum(r["fit_seconds_total"] for r in results["runs"]), 3)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved: {args.out}")
    print(f"Grand total fit() time across all runs: "
          f"{results.get('fit_seconds_grand_total', 0)}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
