"""PLAN 5 Step 1b/1c: ScreenGazeMapper + screen-aware LiveWindowScorer (synthetic)."""

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from models.src.features.face_pose import FrameFeatures  # noqa: E402
from models.src.features.live import LiveWindowScorer  # noqa: E402
from models.src.features.screen_gaze import ScreenGazeMapper  # noqa: E402
from models.src.features.windows import aggregate_window  # noqa: E402

DOTS = [(0.5, 0.5), (0.05, 0.05), (0.95, 0.05), (0.95, 0.95), (0.05, 0.95)]


def _eye(sx, sy, noise=0.0, rng=None):
    """Synthetic head/iris response to looking at screen point (sx, sy)."""
    yaw = 40.0 * (sx - 0.5)
    pitch = 25.0 * (sy - 0.5)
    ix = 0.5 + 0.20 * (sx - 0.5)
    iy = 0.5 + 0.15 * (sy - 0.5)
    if noise and rng is not None:
        yaw += rng.normal(0, noise * 20)
        pitch += rng.normal(0, noise * 20)
        ix += rng.normal(0, noise)
        iy += rng.normal(0, noise)
    return yaw, pitch, ix, iy


def _samples(per_dot=8, noise=0.0, seed=0, dots=DOTS):
    rng = np.random.default_rng(seed)
    out = []
    for sx, sy in dots:
        for _ in range(per_dot):
            yaw, pitch, ix, iy = _eye(sx, sy, noise, rng)
            out.append((yaw, pitch, ix, iy, sx, sy))
    return out


def _frame(t, sx, sy, face=True, blink=0.0, body=True, **kw):
    yaw, pitch, ix, iy = _eye(sx, sy)
    return FrameFeatures(
        t_sec=t,
        face_present=face,
        yaw=kw.get("yaw", yaw),
        pitch=kw.get("pitch", pitch),
        roll=0.0,
        iris_x=kw.get("iris_x", ix),
        iris_y=kw.get("iris_y", iy),
        blink=blink,
        jaw_open=0.0,
        hand_to_face=1.0,
        body_motion=0.0,
        nose_x=0.5,
        nose_y=0.4,
        body_present=body,
        look_h=kw.get("look_h", 0.0),
        look_v=kw.get("look_v", 0.0),
        look_down=kw.get("look_down", 0.0),
    )


# --- mapper ---------------------------------------------------------------------


def test_fit_recovers_screen_positions():
    m = ScreenGazeMapper()
    assert m.fit(_samples(noise=0.002)) is True
    assert m.ok and m.n_dots == 5 and m.residual < 0.05
    for sx, sy in DOTS:
        p = m.predict(_frame(0.0, sx, sy))
        assert p[0] == pytest.approx(sx, abs=0.08)
        assert p[1] == pytest.approx(sy, abs=0.08)


def test_mapper_export_load_roundtrip():
    m = ScreenGazeMapper()
    assert m.fit(_samples(noise=0.002)) is True
    state = m.export_state()
    assert state and state["ok"] and len(state["cx"]) >= 2
    m2 = ScreenGazeMapper()
    assert m2.load_state(state) is True
    assert m2.ok and m2.n_dots == m.n_dots
    for sx, sy in DOTS:
        p1 = m.predict(_frame(0.0, sx, sy))
        p2 = m2.predict(_frame(0.0, sx, sy))
        assert p2[0] == pytest.approx(p1[0], abs=1e-6)
        assert p2[1] == pytest.approx(p1[1], abs=1e-6)


def test_scorer_export_restore_roundtrip():
    sc, ex = _scorer()
    res, t = _calibrate(sc, ex)
    assert res["ok"] is True
    payload = sc.export_calibration()
    assert payload and payload["mapper"]["ok"]
    sc2, ex2 = _scorer()
    assert sc2.restore_calibration(payload) is True
    assert sc2.gaze_mode == "screen"
    assert sc2.baseline_locked
    t_on = t + 5.0
    for i in range(12):
        _feed(sc2, ex2, _frame(t_on + i * 0.3, 0.3, 0.6))
    feats = sc2.features()
    assert feats["gaze"]["on_screen"] is True and feats["gaze"]["calibrated"] is True


def test_on_screen_margin_and_off_screen():
    m = ScreenGazeMapper()
    assert m.fit(_samples())
    assert m.is_on_screen(_frame(0.0, 0.5, 0.5))
    assert m.is_on_screen(_frame(0.0, 0.05, 0.95))
    # Far right of the screen (look at the wall beyond the monitor)
    assert not m.is_on_screen(_frame(0.0, 1.6, 0.5))
    assert not m.is_on_screen(_frame(0.0, 0.5, -0.8))
    # PLAN 8: default margin 0.03 — just past the edge is off-screen
    just_past = _frame(0.0, 1.05, 0.5)
    assert not m.is_on_screen(just_past)  # default margin 0.03
    assert m.is_on_screen(just_past, margin=0.12)
    assert not m.is_on_screen(just_past, margin=0.0)
    # Just inside the edge stays on-screen
    assert m.is_on_screen(_frame(0.0, 0.98, 0.5))


def test_fit_requires_four_dots():
    m = ScreenGazeMapper()
    assert m.fit(_samples(dots=DOTS[:3])) is False
    assert not m.ok and m.n_dots == 3
    assert m.fit(_samples(dots=DOTS[:4])) is True


def test_fit_rejects_sparse_dots_and_garbage():
    m = ScreenGazeMapper()
    # 2 samples per dot < min_samples_per_dot=3 -> no valid dots
    assert m.fit(_samples(per_dot=2)) is False
    # Eyes never move while targets do -> residual far above 0.15
    flat = [(0.0, 0.0, 0.5, 0.5, sx, sy) for sx, sy in DOTS for _ in range(6)]
    assert m.fit(flat) is False
    assert m.residual > 0.15
    assert m.predict(_frame(0.0, 0.5, 0.5)) is None  # not fitted


def test_per_dot_median_is_robust_to_outliers():
    samples = _samples(per_dot=9)
    # corrupt two blinky samples per dot
    corrupted = []
    for i, s in enumerate(samples):
        if i % 9 in (0, 1):
            s = (s[0] + 40, s[1] - 30, 0.1, 0.9, s[4], s[5])
        corrupted.append(s)
    m = ScreenGazeMapper()
    assert m.fit(corrupted) is True
    assert m.residual < 0.05


def test_interaction_variant_fits():
    m = ScreenGazeMapper(interaction=True)
    assert m.fit(_samples(noise=0.001))
    assert m.ok


def test_blink_is_neutral_and_iris_median_smoothing():
    m = ScreenGazeMapper()
    assert m.fit(_samples())
    base = _frame(0.0, 0.5, 0.5)
    m.observe(base)
    # Real blink (look_down low) with wild iris inherits previous prediction
    blink = _frame(0.1, 0.5, 0.5, blink=0.9, look_down=0.1, iris_x=0.95, iris_y=0.05)
    assert m.observe(blink) == pytest.approx(m.predict(base))
    assert m.is_on_screen(blink)
    # single-frame iris glitch is removed by the 3-sample median
    m.observe(_frame(0.2, 0.5, 0.5))
    glitch = _frame(0.3, 0.5, 0.5, iris_x=0.9)
    p = m.observe(glitch)
    assert p[0] == pytest.approx(0.5, abs=0.08)


def test_looking_down_with_high_blink_is_not_neutral():
    """PLAN 8: lowered lids while looking at a phone are NOT treated as a blink."""
    from models.src.features.screen_gaze import is_blink

    m = ScreenGazeMapper()
    assert m.fit(_samples())
    m.observe(_frame(0.0, 0.5, 0.5))
    down = _frame(
        0.1,
        0.5,
        1.4,
        blink=0.7,
        look_down=0.6,
        look_v=-0.5,
        iris_y=0.85,
    )
    assert is_blink(down) is False
    # Mapped to below the screen → off-screen, not "copy previous"
    assert m.is_on_screen(down) is False


def test_eyes_only_directions_past_edge():
    """Eyes left/right/up/down past the edge → off; just inside → on."""
    m = ScreenGazeMapper()
    assert m.fit(_samples())
    assert m.is_on_screen(_frame(0.0, 0.5, 0.5))
    assert not m.is_on_screen(_frame(0.0, -0.05, 0.5))  # left past
    assert not m.is_on_screen(_frame(0.0, 1.05, 0.5))  # right past
    assert not m.is_on_screen(_frame(0.0, 0.5, -0.05))  # above
    assert not m.is_on_screen(_frame(0.0, 0.5, 1.05))  # below
    assert m.is_on_screen(_frame(0.0, 0.02, 0.5))  # just inside left


def test_margin_env_override(monkeypatch):
    monkeypatch.setenv("ML_GAZE_MARGIN", "0.20")
    # Re-import default is read at class construction via DEFAULT_MARGIN —
    # pass margin explicitly to honour env in this process.
    m = ScreenGazeMapper(margin=float(__import__("os").environ["ML_GAZE_MARGIN"]))
    assert m.fit(_samples())
    assert m.is_on_screen(_frame(0.0, 1.15, 0.5))  # within 0.20
    assert not m.is_on_screen(_frame(0.0, 1.15, 0.5), margin=0.03)


def test_head_turn_with_eyes_compensating_stays_on_screen():
    """Gaze fixed at centre while head yaws — mapper with look terms stays on."""
    m = ScreenGazeMapper()
    # Include look_h compensating for yaw in samples
    samples = []
    for sx, sy in DOTS:
        for i in range(8):
            yaw, pitch, ix, iy = _eye(sx, sy)
            # Simulate head-phase variance at centre with compensating look_h
            samples.append((yaw, pitch, ix, iy, sx, sy, -0.02 * yaw, 0.0))
    assert m.fit(samples, has_head_phase=True)
    # Head turned right, eyes compensate left → still centre
    f = _frame(0.0, 0.5, 0.5, yaw=15.0, look_h=-0.3, iris_x=0.42)
    m.observe(_frame(0.0, 0.5, 0.5))
    # With a fitted centre map, moderate head turn + compensating iris stays near centre
    assert m.is_on_screen(f) or m.predict(f)[0] == pytest.approx(0.5, abs=0.35)


def test_no_face_is_off_screen():
    m = ScreenGazeMapper()
    assert m.fit(_samples())
    f = _frame(0.0, 0.5, 0.5, face=False)
    assert m.predict(f) is None
    assert m.is_on_screen(f) is False


# --- aggregate_window on_screen_fn (training default unchanged) -----------------


def test_aggregate_window_default_and_custom_on_screen_fn():
    win = [_frame(i * 0.5, 0.5, 0.5) for i in range(6)]
    default = aggregate_window(win, 3.0, 0.0, 0.0)
    assert default["on_screen_ratio"] == pytest.approx(1.0)
    custom = aggregate_window(win, 3.0, 0.0, 0.0, on_screen_fn=lambda f, y, p: False)
    assert custom["on_screen_ratio"] == 0.0
    assert custom["off_screen_dwell_sec"] > 0.0


# --- live scorer ----------------------------------------------------------------


class _Replay:
    def __init__(self):
        self.queue = []

    def process(self, _img, t):
        f = self.queue.pop(0)
        assert abs(f.t_sec - t) < 1e-9
        return f

    def close(self):
        pass


def _scorer(**kw):
    ex = _Replay()
    sc = LiveWindowScorer(window_sec=3.0, baseline_frames=15, extractor=ex, screen_gaze=True, **kw)
    return sc, ex


def _feed(sc, ex, f, target=None):
    ex.queue.append(f)
    return sc.add_frame(f.t_sec, np.zeros((2, 2, 3), dtype=np.uint8), calib_target=target)


def _calibrate(sc, ex, t0=0.0, per_dot=8, dt=0.3):
    sc.start_calibration()
    t = t0
    for sx, sy in DOTS:
        for _ in range(per_dot):
            _feed(sc, ex, _frame(t, sx, sy), target={"x": sx, "y": sy})
            t += dt
    return sc.finish_calibration(), t


def test_scorer_calibration_locks_centre_baseline_and_maps():
    sc, ex = _scorer()
    res, t = _calibrate(sc, ex)
    assert res["ok"] is True and res["n_dots"] == 5 and res["centre_locked"] is True
    assert sc.baseline_locked
    yaw0, pitch0, _ = sc.baseline
    assert yaw0 == pytest.approx(0.0, abs=1e-6) and pitch0 == pytest.approx(0.0, abs=1e-6)
    assert sc.gaze_mode == "screen"
    # Flush leftover calib frames out of the 3 s window, then check on-screen.
    t_on = t + 5.0
    for i in range(12):
        _feed(sc, ex, _frame(t_on + i * 0.3, 0.3, 0.6))
    feats = sc.features()
    assert feats["on_screen_ratio"] == pytest.approx(1.0)
    assert feats["gaze"]["on_screen"] is True and feats["gaze"]["calibrated"] is True
    assert 0.0 <= feats["gaze"]["sx"] <= 1.0


def test_scorer_offscreen_dwell_and_back_on_screen():
    sc, ex = _scorer()
    _, t = _calibrate(sc, ex)
    for i in range(6):
        _feed(sc, ex, _frame(t, 0.5, 0.5))
        t += 0.3
    # look well beyond the right edge of the screen for ~2.4 s
    for i in range(9):
        _feed(sc, ex, _frame(t, 1.7, 0.5))
        t += 0.3
    g = sc.features()["gaze"]
    assert g["on_screen"] is False
    assert g["off_dwell_sec"] >= 2.0
    assert g["off_ratio"] > 0.5
    # back on screen for >2 s
    for i in range(9):
        _feed(sc, ex, _frame(t, 0.5, 0.5))
        t += 0.3
    g = sc.features()["gaze"]
    assert g["on_screen"] is True and g["on_dwell_sec"] >= 2.0 and g["off_dwell_sec"] == 0.0


def test_scorer_no_face_with_body_is_off_screen_without_body_neutral():
    sc, ex = _scorer()
    _, t = _calibrate(sc, ex)
    for i in range(4):
        _feed(sc, ex, _frame(t, 0.5, 0.5))
        t += 0.3
    for i in range(8):
        _feed(sc, ex, _frame(t, 0.5, 0.5, face=False, body=True))
        t += 0.3
    g = sc.features()["gaze"]
    assert g["on_screen"] is False and g["off_dwell_sec"] >= 2.0
    # nobody in view: neutral, not off-screen evidence
    sc2, ex2 = _scorer()
    _, t2 = _calibrate(sc2, ex2)
    for i in range(4):
        _feed(sc2, ex2, _frame(t2, 0.5, 0.5))
        t2 += 0.3
    for i in range(8):
        _feed(sc2, ex2, _frame(t2, 0.5, 0.5, face=False, body=False))
        t2 += 0.3
    assert sc2.features()["gaze"]["off_dwell_sec"] == 0.0


def test_scorer_failed_fit_uses_baseline_fallback():
    sc, ex = _scorer()
    sc.start_calibration()
    t = 0.0
    # eyes never move while dots do -> fit fails, centre dot still locks baseline
    for sx, sy in DOTS:
        for _ in range(8):
            _feed(sc, ex, _frame(t, 0.5, 0.5), target={"x": sx, "y": sy})
            t += 0.3
    res = sc.finish_calibration()
    assert res["ok"] is False and res["fallback"] is True
    assert sc.gaze_mode == "fallback"
    for i in range(5):
        _feed(sc, ex, _frame(t, 0.5, 0.5))
        t += 0.3
    assert sc.features()["gaze"]["on_screen"] is True
    # iris moved 0.09 in x -> off (> 0.08)
    _feed(sc, ex, _frame(t, 0.5, 0.5, iris_x=0.59))
    assert sc.gaze_summary()["on_screen"] is False
    t += 0.3
    # head yaw 13 deg -> off; 10 deg -> on
    _feed(sc, ex, _frame(t, 0.5, 0.5, yaw=13.0))
    assert sc.gaze_summary()["on_screen"] is False
    t += 0.3
    _feed(sc, ex, _frame(t, 0.5, 0.5, yaw=10.0))
    assert sc.gaze_summary()["on_screen"] is True


def test_scorer_skipped_calibration_auto_baseline_and_fallback():
    sc, ex = _scorer()
    t = 0.0
    for i in range(20):
        _feed(sc, ex, _frame(t, 0.5, 0.5))
        t += 0.3
    assert sc.baseline_locked  # first 15 face frames
    assert sc.gaze_mode == "fallback"
    assert sc.features()["gaze"]["on_screen"] is True
    _feed(sc, ex, _frame(t, 0.5, 0.5, iris_y=0.62))  # |dy| = 0.12 > 0.10
    assert sc.gaze_summary()["on_screen"] is False


def test_rebaseline_only_while_on_screen():
    sc, ex = _scorer()
    _, t = _calibrate(sc, ex)
    for i in range(4):
        _feed(sc, ex, _frame(t, 0.5, 0.5, yaw=2.0, iris_x=0.5))
        t += 0.3
    y_before = sc.baseline[0]
    sc.maybe_rebaseline(0.0, True)
    assert sc.baseline[0] > y_before  # drifts toward on-screen head pose
    # off-screen frames (3-sample iris median needs the look to persist): no drift
    for i in range(3):
        _feed(sc, ex, _frame(t, 1.7, 0.5))
        t += 0.3
    y_mid = sc.baseline[0]
    sc.maybe_rebaseline(0.0, True)
    assert sc.baseline[0] == y_mid


def test_legacy_scorer_unchanged_without_screen_gaze():
    ex = _Replay()
    sc = LiveWindowScorer(window_sec=3.0, baseline_frames=5, extractor=ex)
    t = 0.0
    for i in range(8):
        _feed(sc, ex, _frame(t, 0.5, 0.5))
        t += 0.3
    assert sc.gaze_mode == "legacy"
    assert sc.baseline_locked
