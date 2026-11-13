"""Leakage guards for the nested-LOSO model6 trainer (CPU, synthetic data)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from models.src.features.windows import WINDOW_FEATURE_NAMES  # noqa: E402
from models.src.model6_natural import train as T  # noqa: E402


def _synthetic(n_subjects=4, n_per=40, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_subjects):
        sid = f"S{s:02d}"
        for cond, y in (("focused", 0), ("distracted", 1), ("natural", -1)):
            for i in range(n_per):
                feats = {f: float(rng.normal()) for f in WINDOW_FEATURE_NAMES}
                feats["on_screen_ratio"] = float(np.clip(0.9 - 0.6 * (y == 1) + rng.normal(0, 0.1), 0, 1))
                rows.append(
                    {
                        "subject_id": sid,
                        "condition": cond,
                        "source_file": f"{cond}.mp4",
                        "window_start_sec": float(i),
                        "window_sec": 5.0,
                        "y": y,
                        **feats,
                    }
                )
    return pd.DataFrame(rows)


def test_selector_never_sees_held_out_subject():
    df = _synthetic()
    seen = []

    def spy(train_part, all_part, feats, device, epoch_candidates):
        seen.append((set(train_part["subject_id"]), set(all_part["subject_id"])))
        return T.select_hyperparams(train_part, all_part, feats, device, epoch_candidates)

    folds, preds = T.run_nested_loso(df, torch.device("cpu"), epoch_candidates=(2,), selector=spy)
    held_out = [f["subject_id"] for f in folds]
    assert len(seen) == len(held_out) == 4
    for held, (lab_subj, all_subj) in zip(held_out, seen):
        assert held not in lab_subj
        assert held not in all_subj
    # Every held-out prediction comes from its own fold only.
    assert (preds["fold"] == preds["subject_id"]).all()


def test_replay_hysteresis_ignores_short_glances():
    t = np.arange(0, 10, 1.0)
    p = np.array([0.1, 0.9, 0.1, 0.1, 0.9, 0.9, 0.9, 0.9, 0.1, 0.1])
    out = T.replay_hysteresis(p, t, enter_prob=0.6, enter_sec=2.0, exit_prob=0.4, exit_sec=1.0)
    assert out[1] == 0  # single high step is a glance
    assert out[6] == 1  # held >= 2 s
    assert out[9] == 0  # exits after sustained low


def test_protocol_labels_ignore_features_and_drop_transitions():
    from models.src.model6_natural.extract import label_from_segments

    segs = [(0.0, 60.0, "read", 0), (60.0, 90.0, "phone", 1), (90.0, 120.0, "natural", -1)]
    assert label_from_segments(segs, 10.0, 5.0) == (0, "read")
    assert label_from_segments(segs, 70.0, 5.0) == (1, "phone")
    # Straddles read/phone boundary with both covers < 0.6 → dropped
    assert label_from_segments(segs, 57.5, 5.0) == (None, "transition")
    # Natural phase is unlabelled but keeps its name (used for false alarms)
    assert label_from_segments(segs, 100.0, 5.0) == (None, "natural")


def test_events_counts_onsets_not_windows():
    assert T._events(np.array([0, 1, 1, 1, 0, 1, 0])) == 2


def test_eval_only_rows_excluded_from_fitting():
    df = _synthetic()
    df["eval_only"] = (df["condition"] == "natural").astype(int)
    # Give natural rows real labels — must still be excluded from fit.
    df.loc[df["condition"] == "natural", "y"] = 1
    fit = df[T._fit_mask(df)]
    assert (fit["condition"] != "natural").all()
    assert fit["y"].isin([0, 1]).all()

    def spy(train_part, all_part, feats, device, epoch_candidates):
        assert not (train_part.get("eval_only", pd.Series(0, index=train_part.index)) == 1).any()
        assert "natural" not in set(train_part["condition"])
        return T.select_hyperparams(train_part, all_part, feats, device, epoch_candidates)

    folds, preds = T.run_nested_loso(df, torch.device("cpu"), epoch_candidates=(2,), selector=spy)
    assert len(folds) == 4
    # Held-out predictions still include natural/eval_only rows for scoring.
    assert (preds["condition"] == "natural").any()

def _clip(pred, y, start0=0.0, hop=1.0, win=5.0, sid="S00", src="nat.mp4"):
    n = len(pred)
    return pd.DataFrame(
        {
            "subject_id": sid,
            "source_file": src,
            "window_start_sec": start0 + hop * np.arange(n),
            "window_sec": win,
            "y": y,
            "pred": pred,
        }
    )


def test_fa_events_per_min_counts_onsets_and_minutes():
    # 60 windows at 1 s hop = 1 minute, two onsets
    pred = np.zeros(60, dtype=int)
    pred[5:8] = 1
    pred[30:31] = 1
    df = _clip(pred, np.zeros(60, dtype=int))
    rate, n_ev, minutes = T._fa_events_per_min(df, "pred")
    assert n_ev == 2
    assert minutes == pytest.approx(1.0)
    assert rate == pytest.approx(2.0)
    assert np.isnan(T._fa_events_per_min(df.iloc[0:0], "pred")[0])


def test_span_event_metrics_detection_and_fa_overlap():
    y = np.full(100, -1)
    y[20:30] = 1  # span A (windows 20..29)
    y[60:70] = 1  # span B
    pred = np.zeros(100, dtype=int)
    pred[22:25] = 1  # hits span A
    pred[3:5] = 1  # FA far from any span
    pred[90:92] = 1  # FA
    # onset just before span B within +-2 s slack of its start -> not an FA
    pred[58] = 1
    df = _clip(pred, y, win=1.0)
    m = T._span_event_metrics(df, "pred", slack_sec=2.0)
    assert m["n_spans"] == 2
    assert m["n_spans_detected"] == 1  # span B windows (60..69) have no positive pred
    assert m["span_detection_rate"] == pytest.approx(0.5)
    assert m["n_onsets"] == 4
    assert m["n_fa_onsets"] == 2


def test_positive_spans_split_on_gap_and_label():
    y = np.array([1, 1, 0, 1, 1, 1, -1, 1])
    g = _clip(np.zeros(8, dtype=int), y, win=1.0)
    spans = T._positive_spans(g)
    assert [(a, b) for a, b, _, _ in spans] == [(0, 1), (3, 5), (7, 7)]


def test_natural_event_metrics_reports_span_rate():
    y = np.full(40, -1)
    y[10:20] = 1
    pred = np.zeros(40, dtype=int)
    pred[12:14] = 1
    df = _clip(pred, y, win=1.0)
    df["eval_only"] = 1
    df["pred_mlp_hyst"] = df["pred"]
    m = T._natural_event_metrics(df, "pred_mlp_hyst")
    assert m["span_detection_rate"] == pytest.approx(1.0)
    assert m["fa_events_per_min"] == pytest.approx(0.0)
    assert m["n_pos_spans_windows"] == 10 and m["n_detected"] == 2


def test_pooled_metrics_excludes_eval_only_rows():
    n = 10
    fit = pd.DataFrame(
        {"y": [1, 0] * (n // 2), "eval_only": 0, "pred_mlp": [1, 0] * (n // 2)}
    )
    nat = pd.DataFrame({"y": [1, 1, 0, 0], "eval_only": 1, "pred_mlp": [0, 0, 1, 1]})
    preds = pd.concat([fit, nat], ignore_index=True)
    for c in ("pred_mlp_hyst", "pred_lr", "pred_proxy"):
        preds[c] = preds["pred_mlp"]
    pooled = T.pooled_metrics(preds)
    assert pooled["n_windows"] == n  # natural rows masked out
    assert pooled["mlp_f1_positive"] == pytest.approx(1.0)  # would be < 1 if nat leaked


def test_choose_hysteresis_prefers_fa_feasible_config():
    # Subject with labelled clip + natural negatives whose noisy spikes are 3 s
    # long: low enter_sec fires FA on them; the chooser must pick a feasible
    # config (FA <= 0.5/min) even if a spikier config has higher labelled F1.
    rng = np.random.default_rng(0)
    rows = []
    for sid in ("S00", "S01"):
        n = 120
        y = np.zeros(n, dtype=int)
        y[40:70] = 1
        p = np.where(y == 1, 0.9, 0.1) + rng.normal(0, 0.02, n)
        d = _clip(np.zeros(n, dtype=int), y, win=5.0, sid=sid, src="fit.mp4")
        d["_p"], d["eval_only"], d["condition"] = p, 0, "focused"
        rows.append(d)
        nn = 240
        pn = np.full(nn, 0.05)
        for k in range(10, 230, 20):  # a 4-window (4 s) spike every 20 s
            pn[k : k + 4] = 0.95
        dn = _clip(np.zeros(nn, dtype=int), np.full(nn, -1), win=5.0, sid=sid, src="nat.mp4")
        dn["_p"], dn["eval_only"], dn["condition"] = pn, 1, "natural"
        rows.append(dn)
    df = pd.concat(rows, ignore_index=True)
    params, info = T._choose_hysteresis_info(df, "_p")
    assert info["fa_source"] == "natural"
    assert info["feasible"] is True
    assert info["fa_events_per_min"] <= T.FA_MAX_PER_MIN
    assert params["enter_sec"] >= 3.0  # a 2 s enter window fires on the 4 s natural spikes

    # Never silently default when labelled data exists but nothing is feasible.
    noisy = df.copy()
    noisy.loc[noisy["eval_only"] == 1, "_p"] = 0.95  # permanently "on" -> 1 event total
    p2, info2 = T._choose_hysteresis_info(noisy, "_p", fa_max=-1.0)
    assert info2["feasible"] is False
    assert set(p2) == set(T.DEFAULT_HYST)


def test_downsample_to_hop_keeps_two_second_cadence():
    df = _clip(np.zeros(20, dtype=int), np.zeros(20, dtype=int), hop=0.5)
    out = T._downsample_to_hop(df, 2.0)
    assert np.allclose(np.diff(out["window_start_sec"]), 2.0)


def test_subject_weights_equalise_subjects():
    df = pd.DataFrame({"subject_id": ["a"] * 10 + ["b"] * 20})
    w = T._subject_weights(df)
    assert w.mean() == pytest.approx(1.0)
    assert w[:10].sum() == pytest.approx(w[10:].sum())


def test_platt_calibration_improves_overconfident_scores():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 400)
    p = np.clip(0.5 + (y - 0.5) * 0.9 + rng.normal(0, 0.3, 400), 0.01, 0.99)
    cal = T.fit_platt(p, y)
    assert cal["fitted"] and cal["a"] > 0
    q = T.apply_platt(p, cal)
    assert q.min() >= 0 and q.max() <= 1
    assert np.mean((q - y) ** 2) <= np.mean((p - y) ** 2) + 1e-9
    assert T.fit_platt(p[:5], y[:5])["fitted"] is False
    assert np.array_equal(T.apply_platt(p, T.IDENTITY_CAL), p)


def test_resolve_ablation_groups_and_errors():
    kept = T.resolve_ablation(["blink_rate", "gaze_dev"])
    assert "blink_rate" not in kept
    assert "gaze_dev_mean" not in kept and "gaze_dev_std" not in kept
    assert "perclos" in kept
    with pytest.raises(ValueError):
        T.resolve_ablation(["nope"])
    assert T._parse_csv_arg("S05, S06,") == ["S05", "S06"]


def test_nested_loso_with_ablation_and_deploy_roundtrip(tmp_path):
    df = _synthetic(n_subjects=3, n_per=30)
    df["eval_only"] = (df["condition"] == "natural").astype(int)
    feats = T.resolve_ablation(["blink_rate", "perclos"])
    folds, preds = T.run_nested_loso(
        df, torch.device("cpu"), epoch_candidates=(2,), feats=feats
    )
    assert len(folds) == 3
    assert "calibration_mlp" in folds[0]["chosen"]
    assert "span_detection_rate" in folds[0]["natural_events_mlp"]
    summary = T.summarise(folds, preds)
    assert summary["pooled"]["n_windows"] == int(T._fit_mask(preds).sum())
    path = T.deploy(df, folds, torch.device("cpu"), tmp_path, summary, feats=feats)
    import joblib

    pack = joblib.load(path)
    assert pack["version"] == "v4_nested_loso"
    assert pack["kind"] in ("model6_mlp", "model6_logreg")
    assert pack["features"] == feats
    X = df[feats].fillna(0).astype(np.float32).values[:5]
    proba = pack["model"].predict_proba(X)
    assert proba.shape == (5, 2)
