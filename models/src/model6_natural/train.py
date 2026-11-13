"""Nested leave-one-subject-out training for model6 (v4; PLAN 4 Phase B).

Every choice that affects the reported numbers — decision threshold, epoch
count, hysteresis parameters — is made on the *training* subjects of each
outer fold (inner LOSO). The held-out subject is scored exactly once.

The earlier v2 script picked thresholds on the test fold, selected the
deployed fold by test F1 and gated deployment on a hard-coded baseline; those
numbers are optimistic and are kept only in git history / REPORT_7.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from models.src.features.windows import WINDOW_FEATURE_NAMES, distraction_proxy  # noqa: E402
from models.src.model6_natural.wrapper import (  # noqa: E402
    FusionMLP,
    Model6SklearnWrapper,
    PlattCalibratedProba,
)

VERSION = "v4_nested_loso"
EPOCH_CANDIDATES = (20, 40, 80)
THRESHOLD_GRID = np.round(np.arange(0.05, 0.951, 0.01), 2)
HYST_GRID = {
    "enter_prob": (0.4, 0.5, 0.6, 0.7, 0.8),
    "enter_sec": (2.0, 3.0, 4.0, 6.0),
    "exit_prob": (0.3, 0.4),
    "exit_sec": (2.0,),
}
DEFAULT_HYST = {"enter_prob": 0.6, "enter_sec": 3.0, "exit_prob": 0.4, "exit_sec": 2.0}
# Natural-style false-alarm budget (events / min) for inner-loop selection.
FA_MAX_PER_MIN = 0.5
# Live heartbeat cadence used when replaying hysteresis for selection.
HEARTBEAT_HOP_SEC = 2.0
# Span-overlap slack (seconds) when deciding whether an onset is a false alarm.
SPAN_SLACK_SEC = 2.0
N_BOOT = 2000
SEED = 1234


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _resolve_device(name: str) -> torch.device:
    if name == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("--device cuda requested but torch.cuda.is_available() is False")
        print(f"[train] device=cuda ({torch.cuda.get_device_name(0)})")
        return torch.device("cuda")
    print("[train] device=cpu")
    try:
        torch.use_deterministic_algorithms(True)
    except Exception as exc:  # pragma: no cover - depends on torch build
        print(f"[train] WARNING: deterministic algorithms unavailable: {exc}")
    return torch.device("cpu")


def _parse_csv_arg(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [t.strip() for t in str(value).split(",") if t.strip()]


def resolve_ablation(ablate: Sequence[str], names: Sequence[str] = WINDOW_FEATURE_NAMES) -> List[str]:
    """Features kept after dropping ablated groups.

    A token matches an exact feature name or a group prefix (``gaze_dev`` drops
    ``gaze_dev_mean`` and ``gaze_dev_std``). Unknown tokens raise ``ValueError``.
    """
    drop: set = set()
    for tok in ablate:
        hit = [n for n in names if n == tok or n.startswith(tok + "_")]
        if not hit:
            raise ValueError(f"--ablate: unknown feature/group '{tok}'. Known: {list(names)}")
        drop.update(hit)
    kept = [n for n in names if n not in drop]
    if not kept:
        raise ValueError("--ablate removed every feature")
    return kept


def _subject_weights(df: pd.DataFrame) -> np.ndarray:
    """Per-row inverse-subject-frequency weights, mean 1 (every subject sums equal)."""
    if len(df) == 0:
        return np.zeros(0, dtype=np.float64)
    sid = df["subject_id"].astype(str).to_numpy()
    uniq, inv, counts = np.unique(sid, return_inverse=True, return_counts=True)
    w = len(sid) / (len(uniq) * counts[inv].astype(np.float64))
    return w.astype(np.float64)


# ---------------------------------------------------------------------------
# Platt calibration (1-D logistic on logits)
# ---------------------------------------------------------------------------

IDENTITY_CAL = {"a": 1.0, "b": 0.0, "fitted": False}


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=np.float64), 1e-6, 1 - 1e-6)
    return np.log(p / (1.0 - p))


def fit_platt(
    proba: np.ndarray, y: np.ndarray, sample_weight: Optional[np.ndarray] = None
) -> dict:
    """Fit sigmoid(a*logit(p)+b) on out-of-fold predictions; identity if degenerate."""
    proba = np.asarray(proba, dtype=np.float64)
    y = np.asarray(y).astype(int)
    if len(y) < 10 or len(np.unique(y)) < 2:
        return dict(IDENTITY_CAL)
    try:
        lr = LogisticRegression(C=1e4, max_iter=1000, solver="lbfgs")
        lr.fit(_logit(proba).reshape(-1, 1), y, sample_weight=sample_weight)
    except Exception:
        return dict(IDENTITY_CAL)
    a, b = float(lr.coef_[0, 0]), float(lr.intercept_[0])
    if not np.isfinite(a) or not np.isfinite(b) or a <= 1e-3:
        return dict(IDENTITY_CAL)
    return {"a": a, "b": b, "fitted": True}


def apply_platt(proba: np.ndarray, cal: Optional[dict]) -> np.ndarray:
    proba = np.asarray(proba, dtype=np.float64)
    if not cal or not cal.get("fitted", False):
        return proba
    z = cal["a"] * _logit(proba) + cal["b"]
    return 1.0 / (1.0 + np.exp(-z))


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_REPO, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def _xy(df: pd.DataFrame, feats: List[str]) -> Tuple[np.ndarray, np.ndarray]:
    X = df[feats].fillna(0.0).astype(np.float32).values
    y = df["y"].astype(int).values
    return X, y


def _pick_threshold(
    y_true: np.ndarray, proba: np.ndarray, sample_weight: Optional[np.ndarray] = None
) -> float:
    """Best (optionally sample-weighted) F1 threshold. Training-subject predictions only."""
    if len(np.unique(y_true)) < 2:
        return 0.5
    best_t, best_f1 = 0.5, -1.0
    for t in THRESHOLD_GRID:
        f1 = f1_score(
            y_true,
            (proba >= t).astype(int),
            pos_label=1,
            zero_division=0,
            sample_weight=sample_weight,
        )
        if f1 > best_f1:
            best_f1, best_t = float(f1), float(t)
    return best_t


def _metrics(y_true: np.ndarray, proba: np.ndarray, thr: float) -> Dict[str, float]:
    pred = (proba >= thr).astype(int)
    out = {
        "n": int(len(y_true)),
        "n_pos": int((y_true == 1).sum()),
        "accuracy": float(np.mean(pred == y_true)) if len(y_true) else float("nan"),
        "f1_positive": float(f1_score(y_true, pred, pos_label=1, zero_division=0)),
        "f1_macro": float(f1_score(y_true, pred, average="macro", zero_division=0)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "brier": float(brier_score_loss(y_true, np.clip(proba, 0, 1))) if len(y_true) else float("nan"),
        "roc_auc": float("nan"),
        "pr_auc": float("nan"),
        "threshold": float(thr),
    }
    if out["n_pos"] == 0:
        # No positives in this subject: F1+/recall are undefined, not 0.
        for k in ("f1_positive", "precision", "recall"):
            out[k] = float("nan")
    if len(np.unique(y_true)) > 1:
        out["roc_auc"] = float(roc_auc_score(y_true, proba))
        out["pr_auc"] = float(average_precision_score(y_true, proba))
    return out


def _bootstrap_ci(values: Sequence[float], n_boot: int = N_BOOT, seed: int = SEED) -> List[float]:
    """95% percentile CI of the mean, resampling subjects with replacement."""
    vals = np.array([v for v in values if v == v], dtype=np.float64)
    if len(vals) == 0:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    means = rng.choice(vals, size=(n_boot, len(vals)), replace=True).mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


# ---------------------------------------------------------------------------
# Hysteresis replay (mirrors backend MLService._apply_hysteresis)
# ---------------------------------------------------------------------------


def replay_hysteresis(
    proba: np.ndarray,
    t_sec: np.ndarray,
    enter_prob: float,
    enter_sec: float,
    exit_prob: float,
    exit_sec: float,
) -> np.ndarray:
    """Return 0/1 state per step; same state machine as the live service."""
    state = 0
    high_t0: Optional[float] = None
    low_t0: Optional[float] = None
    out = np.zeros(len(proba), dtype=int)
    for i, (p, t) in enumerate(zip(proba, t_sec)):
        if p >= enter_prob:
            if high_t0 is None:
                high_t0 = t
            low_t0 = None
            if t - high_t0 >= enter_sec:
                state = 1
        elif p < exit_prob:
            if low_t0 is None:
                low_t0 = t
            high_t0 = None
            if t - low_t0 >= exit_sec:
                state = 0
        out[i] = state
    return out


def _events(pred: np.ndarray) -> int:
    """Number of 0→1 onsets (consecutive positives count as one event)."""
    if len(pred) == 0:
        return 0
    p = np.asarray(pred, dtype=int)
    return int(p[0] == 1) + int(np.sum((p[1:] == 1) & (p[:-1] == 0)))


def _clip_groups(df: pd.DataFrame):
    """Yield (clip_df sorted by time, ordering index) per subject/source clip."""
    for _, g in df.groupby(["subject_id", "source_file"], sort=True):
        yield g.sort_values("window_start_sec")


def _apply_hyst_df(df: pd.DataFrame, proba_col: str, params: dict) -> pd.Series:
    out = pd.Series(0, index=df.index, dtype=int)
    for g in _clip_groups(df):
        t = (g["window_start_sec"] + g["window_sec"]).to_numpy(dtype=np.float64)
        out.loc[g.index] = replay_hysteresis(g[proba_col].to_numpy(), t, **params)
    return out


def _fa_events_per_min(df: pd.DataFrame, pred_col: str) -> Tuple[float, int, float]:
    """False-alarm events per minute over clips/rows assumed non-distracted."""
    if df.empty:
        return float("nan"), 0, 0.0
    n_events = 0
    minutes = 0.0
    for g in _clip_groups(df):
        n_events += _events(g[pred_col].to_numpy())
        hop = float(np.median(np.diff(g["window_start_sec"]))) if len(g) > 1 else 1.0
        minutes += len(g) * hop / 60.0
    return float(n_events / max(minutes, 1e-6)), n_events, minutes


def _eval_only_mask(df: pd.DataFrame) -> pd.Series:
    """Rows scored but never fitted: ``eval_only==1`` (or legacy natural condition)."""
    if "eval_only" in df.columns:
        return df["eval_only"].fillna(0).astype(int) == 1
    if "condition" in df.columns:
        return df["condition"].astype(str).str.lower() == "natural"
    return pd.Series(False, index=df.index)


def _downsample_to_hop(df: pd.DataFrame, hop_sec: float) -> pd.DataFrame:
    """Keep windows ~``hop_sec`` apart per clip (live heartbeat cadence)."""
    if df.empty or hop_sec <= 0:
        return df
    keep: List[int] = []
    for g in _clip_groups(df):
        starts = g["window_start_sec"].to_numpy(dtype=np.float64)
        last = -np.inf
        for idx, s in zip(g.index, starts):
            if s - last >= hop_sec - 1e-6:
                keep.append(idx)
                last = s
    return df.loc[sorted(keep)]


def _choose_hysteresis_info(
    df: pd.DataFrame,
    proba_col: str,
    fa_max: float = FA_MAX_PER_MIN,
    hop_sec: float = HEARTBEAT_HOP_SEC,
) -> Tuple[dict, dict]:
    """Pick hysteresis params (training subjects only), replayed at ~heartbeat cadence.

    Objective: maximise subject-weighted labelled-window F1 (fit rows) subject to
    natural-style false alarms <= ``fa_max``/min on eval_only/natural negatives
    (falls back to labelled negatives when no natural rows exist). If no config is
    feasible, the best-F1 config wins; DEFAULT_HYST is used only when there are no
    usable labels at all.
    """
    d = _downsample_to_hop(df, hop_sec)
    fit = _fit_mask(d)
    if fit.sum() == 0 or d.loc[fit, "y"].nunique() < 2:
        return dict(DEFAULT_HYST), {"reason": "no_labelled_data", "feasible": False}

    y_fit = d.loc[fit, "y"].astype(int).to_numpy()
    w_fit = _subject_weights(d.loc[fit])
    nat_neg = _eval_only_mask(d) & (d["y"] != 1)
    if nat_neg.any():
        fa_source = "natural"
        fa_rows = d[nat_neg]
    else:
        fa_source = "labelled_negative"
        fa_rows = d[fit & (d["y"] == 0)]

    best_feas: Optional[Tuple[float, float, dict]] = None  # (f1, fa, params)
    best_any: Optional[Tuple[float, float, dict]] = None
    for ep in HYST_GRID["enter_prob"]:
        for es in HYST_GRID["enter_sec"]:
            for xp in HYST_GRID["exit_prob"]:
                if xp > ep:
                    continue
                for xs in HYST_GRID["exit_sec"]:
                    params = {"enter_prob": ep, "enter_sec": es, "exit_prob": xp, "exit_sec": xs}
                    state = _apply_hyst_df(d, proba_col, params)
                    f1 = float(
                        f1_score(y_fit, state[fit].to_numpy(), zero_division=0, sample_weight=w_fit)
                    )
                    fa = float("nan")
                    if len(fa_rows):
                        fa, _, _ = _fa_events_per_min(fa_rows.assign(_s=state[fa_rows.index]), "_s")
                    feasible = (fa != fa) or fa <= fa_max
                    fa_v = 0.0 if fa != fa else fa
                    if best_any is None or f1 > best_any[0]:
                        best_any = (f1, fa_v, params)
                    if feasible and (
                        best_feas is None
                        or f1 > best_feas[0]
                        or (f1 == best_feas[0] and fa_v < best_feas[1])
                    ):
                        best_feas = (f1, fa_v, params)
    chosen = best_feas if best_feas is not None else best_any
    assert chosen is not None
    info = {
        "feasible": best_feas is not None,
        "fa_source": fa_source,
        "fa_max": float(fa_max),
        "hop_sec": float(hop_sec),
        "f1": float(chosen[0]),
        "fa_events_per_min": float(chosen[1]),
    }
    return dict(chosen[2]), info


def _choose_hysteresis(df: pd.DataFrame, proba_col: str) -> dict:
    """FA-constrained max-F1 hysteresis params (see ``_choose_hysteresis_info``)."""
    return _choose_hysteresis_info(df, proba_col)[0]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def fit_mlp(
    Xtr: np.ndarray,
    ytr: np.ndarray,
    device: torch.device,
    epochs: int,
    seed: int = SEED,
    batch_size: int = 64,
    lr: float = 1e-3,
    sample_weight: Optional[np.ndarray] = None,
) -> Tuple[FusionMLP, StandardScaler]:
    _seed_all(seed)
    scaler = StandardScaler()
    Xtr_s = scaler.fit_transform(Xtr).astype(np.float32)

    model = FusionMLP(n_in=Xtr_s.shape[1]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    n_pos = max(int((ytr == 1).sum()), 1)
    n_neg = max(int((ytr == 0).sum()), 1)
    pos_weight = torch.tensor([n_neg / n_pos], device=device, dtype=torch.float32)
    crit = nn.BCEWithLogitsLoss(pos_weight=pos_weight, reduction="none")

    w = (
        np.ones(len(ytr), dtype=np.float32)
        if sample_weight is None
        else np.asarray(sample_weight, dtype=np.float32)
    )
    ds = TensorDataset(
        torch.from_numpy(Xtr_s), torch.from_numpy(ytr.astype(np.float32)), torch.from_numpy(w)
    )
    gen = torch.Generator().manual_seed(seed)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=True, generator=gen)

    model.train()
    for _ in range(epochs):
        for xb, yb, wb in loader:
            xb, yb, wb = xb.to(device), yb.to(device), wb.to(device)
            opt.zero_grad(set_to_none=True)
            loss = (crit(model(xb), yb) * wb).sum() / wb.sum().clamp_min(1e-8)
            loss.backward()
            opt.step()
    model.eval()
    return model, scaler


def predict_mlp(model: FusionMLP, scaler: StandardScaler, X: np.ndarray, device) -> np.ndarray:
    if len(X) == 0:
        return np.zeros(0, dtype=np.float64)
    with torch.no_grad():
        xt = torch.from_numpy(scaler.transform(X).astype(np.float32)).to(device)
        return torch.sigmoid(model(xt).float()).cpu().numpy().astype(np.float64)


def fit_lr(
    Xtr: np.ndarray, ytr: np.ndarray, sample_weight: Optional[np.ndarray] = None
) -> Pipeline:
    lr = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", solver="lbfgs")),
        ]
    )
    if sample_weight is None:
        lr.fit(Xtr, ytr)
    else:
        lr.fit(Xtr, ytr, clf__sample_weight=np.asarray(sample_weight, dtype=np.float64))
    return lr


def proxy_scores(df: pd.DataFrame) -> np.ndarray:
    """Hand-written rule score in [0,1] (baseline; also the old label generator)."""
    raw = np.array([distraction_proxy(r) for r in df.to_dict("records")], dtype=np.float64)
    return np.clip(raw / 2.0, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Nested LOSO
# ---------------------------------------------------------------------------


def select_hyperparams(
    train_part: pd.DataFrame,
    all_part: pd.DataFrame,
    feats: List[str],
    device: torch.device,
    epoch_candidates: Sequence[int] = EPOCH_CANDIDATES,
) -> dict:
    """Inner LOSO over the subjects in ``train_part`` only.

    ``train_part`` holds labelled rows of the outer-training subjects;
    ``all_part`` holds every row (incl. unlabelled) of the same subjects, used
    to replay hysteresis over full clips. Neither may contain the outer
    held-out subject — enforced by the caller and checked here.
    """
    subjects = sorted(train_part["subject_id"].unique())
    assert set(all_part["subject_id"].unique()) <= set(subjects)

    if len(subjects) < 2:
        # Cannot do an inner split: fall back to defaults (reported as such).
        return {
            "epochs": int(np.median(epoch_candidates)),
            "threshold": 0.5,
            "lr_threshold": 0.5,
            "proxy_threshold": 0.5,
            "hysteresis": dict(DEFAULT_HYST),
            "calibration_mlp": dict(IDENTITY_CAL),
            "calibration_lr": dict(IDENTITY_CAL),
            "inner_folds": 0,
        }

    oof = {e: pd.Series(np.nan, index=all_part.index) for e in epoch_candidates}
    oof_lr = pd.Series(np.nan, index=all_part.index)
    for inner in subjects:
        tr = train_part[train_part["subject_id"] != inner]
        if tr["y"].nunique() < 2:
            continue
        te_all = all_part[all_part["subject_id"] == inner]
        Xtr, ytr = _xy(tr, feats)
        w_tr = _subject_weights(tr)
        Xte = te_all[feats].fillna(0.0).astype(np.float32).values
        for e in epoch_candidates:
            model, scaler = fit_mlp(Xtr, ytr, device, epochs=e, sample_weight=w_tr)
            oof[e].loc[te_all.index] = predict_mlp(model, scaler, Xte, device)
        oof_lr.loc[te_all.index] = fit_lr(Xtr, ytr, sample_weight=w_tr).predict_proba(Xte)[:, 1]

    lab_idx = train_part.index
    y_lab = train_part["y"].astype(int).to_numpy()
    w_lab = _subject_weights(train_part)

    def _calibrate(series: pd.Series) -> Tuple[pd.Series, dict]:
        """Platt-fit on labelled OOF rows, then apply to every OOF row."""
        p = series.loc[lab_idx].to_numpy()
        ok = ~np.isnan(p)
        cal = fit_platt(p[ok], y_lab[ok], w_lab[ok]) if ok.any() else dict(IDENTITY_CAL)
        return pd.Series(apply_platt(series.to_numpy(), cal), index=series.index), cal

    best_e, best_f1, best_thr = epoch_candidates[0], -1.0, 0.5
    best_cal, best_series = dict(IDENTITY_CAL), oof[epoch_candidates[0]]
    for e in epoch_candidates:
        p_cal, cal = _calibrate(oof[e])
        p = p_cal.loc[lab_idx].to_numpy()
        ok = ~np.isnan(p)
        if ok.sum() == 0:
            continue
        thr = _pick_threshold(y_lab[ok], p[ok], w_lab[ok])
        f1 = f1_score(
            y_lab[ok], (p[ok] >= thr).astype(int), zero_division=0, sample_weight=w_lab[ok]
        )
        if f1 > best_f1:
            best_e, best_f1, best_thr = e, float(f1), thr
            best_cal, best_series = cal, p_cal

    lr_cal_series, lr_cal = _calibrate(oof_lr)
    p_lr = lr_cal_series.loc[lab_idx].to_numpy()
    ok = ~np.isnan(p_lr)
    lr_thr = _pick_threshold(y_lab[ok], p_lr[ok], w_lab[ok]) if ok.any() else 0.5
    # The rule has no fitted parameters, so its threshold may use all training subjects.
    proxy_thr = _pick_threshold(y_lab, proxy_scores(train_part), w_lab)

    hyst_df = all_part.assign(_p=best_series).dropna(subset=["_p"])
    hyst, hyst_info = _choose_hysteresis_info(hyst_df, "_p")

    return {
        "epochs": int(best_e),
        "threshold": float(best_thr),
        "inner_f1": float(best_f1),
        "lr_threshold": float(lr_thr),
        "proxy_threshold": float(proxy_thr),
        "hysteresis": hyst,
        "hysteresis_info": hyst_info,
        "calibration_mlp": best_cal,
        "calibration_lr": lr_cal,
        "inner_folds": len(subjects),
    }


def _fit_mask(df: pd.DataFrame) -> pd.Series:
    """Rows eligible for hyperparam selection and final fitting.

    Human-annotation natural clips carry y∈{0,1} but ``eval_only=1`` so they
    must not enter training — only per-held-out scoring.
    """
    labelled = df["y"].isin([0, 1])
    if "eval_only" in df.columns:
        return labelled & (df["eval_only"].fillna(0).astype(int) == 0)
    # Legacy CSVs without the column: natural condition is never in-train.
    if "condition" in df.columns:
        return labelled & (df["condition"].astype(str).str.lower() != "natural")
    return labelled


def _positive_spans(g: pd.DataFrame) -> List[Tuple[int, int, float, float]]:
    """Contiguous runs of y==1 windows in a time-sorted clip.

    Returns ``(first_pos, last_pos, t_start, t_end)`` with positions into ``g`` and
    the span's time extent (first window start .. last window end). Adjacent
    positive windows belong to one span; a negative/unlabelled window or a time
    gap (next window starts after the previous ended) closes it.
    """
    y = g["y"].to_numpy()
    starts = g["window_start_sec"].to_numpy(dtype=np.float64)
    ends = starts + g["window_sec"].to_numpy(dtype=np.float64)
    spans: List[Tuple[int, int, float, float]] = []
    i, n = 0, len(g)
    while i < n:
        if y[i] != 1:
            i += 1
            continue
        j = i
        while j + 1 < n and y[j + 1] == 1 and starts[j + 1] <= ends[j] + 1e-6:
            j += 1
        spans.append((i, j, float(starts[i]), float(ends[j])))
        i = j + 1
    return spans


def _span_event_metrics(
    df: pd.DataFrame, pred_col: str, slack_sec: float = SPAN_SLACK_SEC
) -> dict:
    """Span detection rate + span-aware false alarms per minute.

    * Span = contiguous ``y==1`` windows within a clip.
    * Detected = at least one positive prediction inside the span's windows.
    * False-alarm onset = 0->1 prediction onset (at the window end time, as in the
      live replay) that does not fall within any positive span ± ``slack_sec``.
      Counted over the full clip sequence (labelled and unlabelled windows).
    """
    n_spans = n_hit = n_onsets = n_fa = 0
    minutes = 0.0
    for g in _clip_groups(df):
        g = g.reset_index(drop=True)
        pred = g[pred_col].to_numpy().astype(int)
        spans = _positive_spans(g)
        n_spans += len(spans)
        n_hit += sum(int((pred[a : b + 1] == 1).any()) for a, b, _, _ in spans)
        starts = g["window_start_sec"].to_numpy(dtype=np.float64)
        ends = starts + g["window_sec"].to_numpy(dtype=np.float64)
        onset_idx = [
            i for i in range(len(pred)) if pred[i] == 1 and (i == 0 or pred[i - 1] == 0)
        ]
        n_onsets += len(onset_idx)
        for i in onset_idx:
            t = ends[i]
            if not any(ts - slack_sec <= t <= te + slack_sec for _, _, ts, te in spans):
                n_fa += 1
        hop = float(np.median(np.diff(starts))) if len(g) > 1 else 1.0
        minutes += len(g) * hop / 60.0
    return {
        "n_spans": int(n_spans),
        "n_spans_detected": int(n_hit),
        "span_detection_rate": float(n_hit / n_spans) if n_spans else float("nan"),
        "n_onsets": int(n_onsets),
        "n_fa_onsets": int(n_fa),
        "fa_events_per_min": float(n_fa / max(minutes, 1e-6)) if minutes > 0 else float("nan"),
        "minutes": float(minutes),
    }


def _natural_event_metrics(te_all: pd.DataFrame, pred_col: str) -> dict:
    """Natural-clip metrics: span detection, span-aware FA/min, window-level recall.

    ``fa_events_per_min`` counts onsets outside any annotated positive span ±2 s
    over the full natural sequence. ``fa_events_per_min_neg_only`` keeps the
    older negatives-only count for continuity.
    """
    nat = te_all[_eval_only_mask(te_all)].copy()
    if nat.empty:
        return {
            "fa_events_per_min": float("nan"),
            "fa_events_per_min_neg_only": float("nan"),
            "detection_rate": float("nan"),
            "span_detection_rate": float("nan"),
            "n_spans": 0,
            "n_spans_detected": 0,
            "n_onsets": 0,
            "n_fa_onsets": 0,
            "n_pos_spans_windows": 0,
            "n_detected": 0,
            "minutes": 0.0,
        }
    sm = _span_event_metrics(nat, pred_col)
    neg = nat[nat["y"] != 1]
    fa_neg, _, _ = _fa_events_per_min(neg, pred_col)
    pos = nat[nat["y"] == 1]
    n_pos = int(len(pos))
    n_hit = int((pos[pred_col] == 1).sum()) if n_pos else 0
    return {
        **sm,
        "fa_events_per_min_neg_only": fa_neg,
        "detection_rate": float(n_hit / n_pos) if n_pos else float("nan"),
        "n_pos_spans_windows": n_pos,
        "n_detected": n_hit,
    }


def run_nested_loso(
    df: pd.DataFrame,
    device: torch.device,
    epoch_candidates: Sequence[int] = EPOCH_CANDIDATES,
    selector: Callable[..., dict] = select_hyperparams,
    feats: Optional[Sequence[str]] = None,
) -> Tuple[List[dict], pd.DataFrame]:
    """Outer LOSO. Returns per-fold metric dicts and all held-out predictions."""
    feats = list(feats) if feats is not None else list(WINDOW_FEATURE_NAMES)
    fit_rows = df[_fit_mask(df)]
    subjects = sorted(fit_rows["subject_id"].unique().tolist())
    if len(subjects) < 2:
        raise RuntimeError(f"Need >=2 subjects with fit labels, got {subjects}")

    folds: List[dict] = []
    preds: List[pd.DataFrame] = []
    for held in subjects:
        tr_lab = fit_rows[fit_rows["subject_id"] != held]
        # All rows of training subjects (incl. eval_only natural clips) feed the inner
        # hysteresis/FA selection; eval_only rows are never fitted (tr_lab excludes them).
        tr_clip = df[df["subject_id"] != held]
        te_all = df[df["subject_id"] == held].copy()
        te_fit_mask = _fit_mask(te_all)
        if tr_lab["y"].nunique() < 2 or not te_fit_mask.any():
            print(f"[train] skip {held}: insufficient labels")
            continue
        assert held not in set(tr_lab["subject_id"]) and held not in set(tr_clip["subject_id"])

        print(f"\n[train] outer fold: hold out {held}")
        hp = selector(tr_lab, tr_clip, feats, device, epoch_candidates)
        print(
            f"  inner choice: epochs={hp['epochs']} thr={hp['threshold']:.2f} "
            f"hyst={hp['hysteresis']}"
        )

        Xtr, ytr = _xy(tr_lab, feats)
        w_tr = _subject_weights(tr_lab)
        Xte = te_all[feats].fillna(0.0).astype(np.float32).values
        model, scaler = fit_mlp(Xtr, ytr, device, epochs=hp["epochs"], sample_weight=w_tr)
        te_all["p_mlp"] = apply_platt(
            predict_mlp(model, scaler, Xte, device), hp.get("calibration_mlp")
        )
        te_all["p_lr"] = apply_platt(
            fit_lr(Xtr, ytr, sample_weight=w_tr).predict_proba(Xte)[:, 1],
            hp.get("calibration_lr"),
        )
        te_all["p_proxy"] = proxy_scores(te_all)
        te_all["p_majority"] = float(np.mean(ytr))
        te_all["pred_mlp"] = (te_all["p_mlp"] >= hp["threshold"]).astype(int)
        te_all["pred_lr"] = (te_all["p_lr"] >= hp["lr_threshold"]).astype(int)
        te_all["pred_proxy"] = (te_all["p_proxy"] >= hp["proxy_threshold"]).astype(int)
        te_all["pred_majority"] = int(np.mean(ytr) >= 0.5)
        te_all["pred_mlp_hyst"] = _apply_hyst_df(te_all, "p_mlp", hp["hysteresis"])

        te_lab = te_all[te_fit_mask]
        y = te_lab["y"].astype(int).to_numpy()
        fold = {
            "subject_id": held,
            "n_train": int(len(tr_lab)),
            "chosen": hp,
            "mlp": _metrics(y, te_lab["p_mlp"].to_numpy(), hp["threshold"]),
            "logreg": _metrics(y, te_lab["p_lr"].to_numpy(), hp["lr_threshold"]),
            "rule_proxy": _metrics(y, te_lab["p_proxy"].to_numpy(), hp["proxy_threshold"]),
            "majority": _metrics(
                y, te_lab["p_majority"].to_numpy(), 0.5
            ),
            "mlp_hysteresis_f1": float(
                f1_score(y, te_lab["pred_mlp_hyst"].to_numpy(), zero_division=0)
            ) if (y == 1).any() else float("nan"),
        }
        # False alarms: natural clip (eval_only) and labelled-negative fit rows.
        nat = te_all[_eval_only_mask(te_all)]
        neg = te_lab[te_lab["y"] == 0]
        for name, part in (("natural", nat), ("labelled_negative", neg)):
            for col in ("pred_mlp", "pred_mlp_hyst"):
                rate, n_ev, mins = _fa_events_per_min(part, col)
                fold[f"fa_events_per_min_{name}_{col}"] = rate
            fold[f"minutes_{name}"] = _fa_events_per_min(part, "pred_mlp")[2]
        fold["natural_events_mlp"] = _natural_event_metrics(te_all, "pred_mlp_hyst")

        folds.append(fold)
        preds.append(te_all.assign(fold=held))
        m = fold["mlp"]
        print(
            f"  MLP F1+={m['f1_positive']:.3f} P={m['precision']:.3f} R={m['recall']:.3f} "
            f"ROC={m['roc_auc']:.3f} | LR F1+={fold['logreg']['f1_positive']:.3f} "
            f"| rule F1+={fold['rule_proxy']['f1_positive']:.3f} "
            f"| hyst F1+={fold['mlp_hysteresis_f1']:.3f}"
        )

    if not folds:
        raise RuntimeError("No outer folds completed")
    return folds, pd.concat(preds)


def _safe_f1(y: np.ndarray, pred) -> float:
    return float(f1_score(y, pred, zero_division=0)) if len(y) else float("nan")


def pooled_metrics(preds: pd.DataFrame) -> dict:
    """Pooled F1+ over fit-eligible held-out rows only (eval_only natural excluded)."""
    lab = preds[_fit_mask(preds)]
    y = lab["y"].astype(int).to_numpy()
    return {
        "n_windows": int(len(lab)),
        "n_pos": int((y == 1).sum()),
        "mlp_f1_positive": _safe_f1(y, lab["pred_mlp"]),
        "mlp_hyst_f1_positive": _safe_f1(y, lab["pred_mlp_hyst"]),
        "logreg_f1_positive": _safe_f1(y, lab["pred_lr"]),
        "rule_proxy_f1_positive": _safe_f1(y, lab["pred_proxy"]),
    }


def natural_clip_metrics(preds: pd.DataFrame) -> dict:
    """Pooled window-level metrics on annotated natural (eval_only) clips, kept separate."""
    nat = preds[_eval_only_mask(preds) & preds["y"].isin([0, 1])]
    y = nat["y"].astype(int).to_numpy()
    out = {
        "n_windows": int(len(nat)),
        "n_pos": int((y == 1).sum()),
        "mlp_f1_positive": float("nan"),
        "mlp_hyst_f1_positive": float("nan"),
        "mlp_pr_auc": float("nan"),
        "mlp_roc_auc": float("nan"),
    }
    if len(nat):
        out["mlp_f1_positive"] = _safe_f1(y, nat["pred_mlp"])
        out["mlp_hyst_f1_positive"] = _safe_f1(y, nat["pred_mlp_hyst"])
        if len(np.unique(y)) > 1:
            out["mlp_pr_auc"] = float(average_precision_score(y, nat["p_mlp"]))
            out["mlp_roc_auc"] = float(roc_auc_score(y, nat["p_mlp"]))
    return out


def summarise(folds: List[dict], preds: pd.DataFrame) -> dict:
    summary: Dict[str, dict] = {}
    for model in ("mlp", "logreg", "rule_proxy", "majority"):
        per = {k: [f[model][k] for f in folds] for k in ("f1_positive", "f1_macro", "precision", "recall", "roc_auc", "pr_auc", "brier")}
        summary[model] = {
            k: {
                "mean": float(np.nanmean(v)) if np.any(np.isfinite(v)) else float("nan"),
                "std": float(np.nanstd(v)) if np.any(np.isfinite(v)) else float("nan"),
                "ci95_over_subjects": _bootstrap_ci(v),
            }
            for k, v in per.items()
        }
    summary["pooled"] = pooled_metrics(preds)
    summary["natural_clips"] = natural_clip_metrics(preds)
    fa_keys = [k for k in folds[0] if k.startswith("fa_events_per_min_")]
    summary["false_alarms"] = {
        k: float(np.nanmean([f[k] for f in folds])) for k in fa_keys
    }
    summary["mlp_hysteresis_f1"] = {
        "mean": float(np.nanmean([f["mlp_hysteresis_f1"] for f in folds])),
        "n_subjects_with_positives": int(sum(f["mlp"]["n_pos"] > 0 for f in folds)),
        "ci95_over_subjects": _bootstrap_ci([f["mlp_hysteresis_f1"] for f in folds]),
    }
    if any("natural_events_mlp" in f for f in folds):
        nev = [f["natural_events_mlp"] for f in folds if "natural_events_mlp" in f]

        def _mean(vals):
            arr = np.array(vals, dtype=np.float64)
            return float(np.nanmean(arr)) if np.isfinite(arr).any() else float("nan")

        dets = [e["detection_rate"] for e in nev]
        span_dets = [e.get("span_detection_rate", float("nan")) for e in nev]
        fas = [e["fa_events_per_min"] for e in nev]
        summary["natural_events"] = {
            "detection_rate_mean": _mean(dets),
            "span_detection_rate_mean": _mean(span_dets),
            "fa_events_per_min_mean": _mean(fas),
            "n_spans_total": int(sum(e.get("n_spans", 0) for e in nev)),
            "n_spans_detected_total": int(sum(e.get("n_spans_detected", 0) for e in nev)),
            "detection_rate_ci95": _bootstrap_ci(dets),
            "span_detection_rate_ci95": _bootstrap_ci(span_dets),
            "fa_events_per_min_ci95": _bootstrap_ci(fas),
        }
    return summary


def _median_calibration(folds: List[dict], key: str) -> Optional[dict]:
    """Median Platt params over folds that actually fitted one (None if none did)."""
    cals = [f["chosen"].get(key) for f in folds]
    cals = [c for c in cals if c and c.get("fitted")]
    if not cals:
        return None
    return {
        "a": float(np.median([c["a"] for c in cals])),
        "b": float(np.median([c["b"] for c in cals])),
        "fitted": True,
        "n_folds": len(cals),
    }


def deploy(
    df: pd.DataFrame,
    folds: List[dict],
    device: torch.device,
    ckpt_dir: Path,
    summary: dict,
    feats: Optional[Sequence[str]] = None,
) -> Path:
    """Train on all fit-eligible subjects using the median of inner-chosen settings.

    If packing logistic regression beats the MLP on mean nested-LOSO F1+, the
    deployed pack is an LR pipeline (rule fixed before looking at test numbers).
    Platt params (median of the inner out-of-fold fits) are stored in the pack
    and applied by the packed model's ``predict_proba``, so the stored
    threshold/hysteresis live on calibrated probabilities.
    """
    feats = list(feats) if feats is not None else list(WINDOW_FEATURE_NAMES)
    labelled = df[_fit_mask(df)]
    epochs = int(np.median([f["chosen"]["epochs"] for f in folds]))
    thr = float(np.median([f["chosen"]["threshold"] for f in folds]))
    hyst = {
        k: float(np.median([f["chosen"]["hysteresis"][k] for f in folds]))
        for k in DEFAULT_HYST
    }
    mlp_f1 = float(summary.get("mlp", {}).get("f1_positive", {}).get("mean", float("nan")))
    lr_f1 = float(summary.get("logreg", {}).get("f1_positive", {}).get("mean", float("nan")))
    use_lr = (lr_f1 == lr_f1) and (mlp_f1 != mlp_f1 or lr_f1 > mlp_f1)
    Xall, yall = _xy(labelled, feats)
    w_all = _subject_weights(labelled)
    if use_lr:
        lr_thr = float(np.median([f["chosen"]["lr_threshold"] for f in folds]))
        cal = _median_calibration(folds, "calibration_lr")
        pipe = fit_lr(Xall, yall, sample_weight=w_all)
        model = PlattCalibratedProba(pipe, cal["a"], cal["b"]) if cal else pipe
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        pack_path = ckpt_dir / "model.pkl"
        joblib.dump(
            {
                "model": model,
                "threshold": lr_thr,
                "hysteresis": hyst,
                "features": feats,
                "kind": "model6_logreg",
                "version": VERSION,
                "calibration": cal,
                "metrics_summary": {"logreg": summary["logreg"], "mlp": summary["mlp"]},
                "deploy_reason": f"logreg mean F1+ {lr_f1:.4f} > mlp {mlp_f1:.4f}",
            },
            pack_path,
        )
        print(
            f"[train] deployed LOGREG pack -> {pack_path} "
            f"(thr={lr_thr:.2f}, hyst={hyst}, cal={cal}, lr_f1={lr_f1:.3f} > mlp_f1={mlp_f1:.3f})"
        )
        return pack_path
    cal = _median_calibration(folds, "calibration_mlp")
    model, scaler = fit_mlp(Xall, yall, device, epochs=epochs, sample_weight=w_all)
    pack = {
        "kind": "model6_mlp",
        "version": VERSION,
        "features": feats,
        "threshold": thr,
        "hysteresis": hyst,
        "epochs": epochs,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
        "hidden": 64,
        "calibration": cal,
    }
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    pack_path = ckpt_dir / "model.pkl"
    joblib.dump(
        {
            "model": Model6SklearnWrapper(pack),
            "threshold": thr,
            "hysteresis": hyst,
            "features": feats,
            "kind": "model6_mlp",
            "version": VERSION,
            "calibration": cal,
            "metrics_summary": {"mlp": summary["mlp"]},
        },
        pack_path,
    )
    torch.save(pack, ckpt_dir / "model6_mlp.pt")
    print(
        f"[train] deployed pack -> {pack_path} "
        f"(epochs={epochs}, thr={thr:.2f}, hyst={hyst}, cal={cal})"
    )
    return pack_path


def run(
    windows_csv: Path,
    out_dir: Path,
    ckpt_dir: Path,
    device_name: str,
    window_sec_filter: Optional[float],
    epoch_candidates: Sequence[int] = EPOCH_CANDIDATES,
    exclude_subjects: Sequence[str] = (),
    ablate: Sequence[str] = (),
) -> dict:
    device = _resolve_device(device_name)
    feats = resolve_ablation(ablate)
    df = pd.read_csv(windows_csv)
    for c in list(WINDOW_FEATURE_NAMES) + ["subject_id", "y", "condition", "source_file", "window_start_sec", "window_sec"]:
        if c not in df.columns:
            raise ValueError(f"windows.csv missing column: {c}")
    if window_sec_filter is not None:
        df = df[np.isclose(df["window_sec"], window_sec_filter)].copy()
        print(f"[train] window_sec={window_sec_filter} -> {len(df)} rows")
    excl = {s.strip().upper() for s in exclude_subjects if s.strip()}
    if excl:
        before = df["subject_id"].astype(str).str.upper().unique().tolist()
        unknown = sorted(excl - set(before))
        if unknown:
            print(f"[train] WARNING: --exclude-subjects not present in data: {unknown}")
        df = df[~df["subject_id"].astype(str).str.upper().isin(excl)].copy()
        print(f"[train] excluded subjects {sorted(excl)} -> {len(df)} rows")
    if ablate:
        print(f"[train] ablate={list(ablate)} -> {len(feats)} features: {feats}")
    df = df.reset_index(drop=True)

    folds, preds = run_nested_loso(df, device, epoch_candidates, feats=feats)
    summary = summarise(folds, preds)

    meta_path = windows_csv.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    result = {
        "protocol": (
            "nested leave-one-subject-out (inner LOSO selects epochs, threshold, Platt "
            f"calibration, hysteresis; FA<={FA_MAX_PER_MIN}/min constrained, "
            f"replay hop~{HEARTBEAT_HOP_SEC}s; per-subject inverse-frequency weights)"
        ),
        "version": VERSION,
        "git_hash": _git_hash(),
        "seed": SEED,
        "device": device.type,
        "windows_csv": str(windows_csv),
        "label_source": meta.get("label_source", "rule (circular — see windows.label_window_row)"),
        "target_fps": meta.get("target_fps"),
        "window_sec_filter": window_sec_filter,
        "exclude_subjects": sorted(excl),
        "ablated": list(ablate),
        "features": feats,
        "n_subjects": len(folds),
        "epoch_candidates": list(epoch_candidates),
        "summary": summary,
        "folds": folds,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    keep = [
        "subject_id", "condition", "source_file", "window_start_sec", "window_sec", "y", "fold",
        "p_mlp", "p_lr", "p_proxy", "pred_mlp", "pred_mlp_hyst", "pred_lr", "pred_proxy",
    ]
    if "eval_only" in preds.columns:
        keep.insert(6, "eval_only")
    preds[keep].to_csv(out_dir / "fold_predictions.csv", index=False)
    result["checkpoint"] = str(deploy(df, folds, device, ckpt_dir, summary, feats=feats))
    (out_dir / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n[train] wrote {out_dir / 'metrics.json'}")
    s = summary["mlp"]
    print(
        f"[train] MLP F1+ mean={s['f1_positive']['mean']:.3f} "
        f"CI95={s['f1_positive']['ci95_over_subjects']} | "
        f"rule F1+={summary['rule_proxy']['f1_positive']['mean']:.3f} | "
        f"LR F1+={summary['logreg']['f1_positive']['mean']:.3f}"
    )
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Train model6 with nested LOSO (v4)")
    p.add_argument(
        "--windows",
        type=Path,
        default=_REPO / "models" / "data" / "processed" / "model6_natural" / "windows.csv",
    )
    p.add_argument("--out-dir", type=Path, default=_REPO / "models" / "reports" / "model6_v4")
    p.add_argument(
        "--ckpt-dir",
        type=Path,
        default=_REPO / "models" / "outputs" / "checkpoints" / "model6_v4",
    )
    p.add_argument(
        "--device",
        choices=("cuda", "cpu"),
        default="cuda",
        help="cpu additionally enables torch.use_deterministic_algorithms(True)",
    )
    p.add_argument(
        "--window-sec",
        type=float,
        default=5.0,
        help="Train on this window length only (default 5s). Use 0 for all.",
    )
    p.add_argument(
        "--exclude-subjects",
        type=str,
        default="",
        help="Comma-separated subject ids to drop entirely (e.g. S05,S06)",
    )
    p.add_argument(
        "--ablate",
        type=str,
        default="",
        help="Comma-separated features/groups to drop (e.g. blink_rate,perclos)",
    )
    args = p.parse_args(argv)
    if not args.windows.exists():
        raise FileNotFoundError(
            f"Missing {args.windows}. Run: python -m models.src.model6_natural.extract"
        )
    wfilter = None if args.window_sec <= 0 else float(args.window_sec)
    run(
        args.windows,
        args.out_dir,
        args.ckpt_dir,
        args.device,
        wfilter,
        exclude_subjects=_parse_csv_arg(args.exclude_subjects),
        ablate=_parse_csv_arg(args.ablate),
    )


if __name__ == "__main__":
    main()
