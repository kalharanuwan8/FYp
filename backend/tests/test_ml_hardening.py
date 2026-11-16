"""Hardening of the live ML path: no client-reported focus, no invented
confidences, bounded payloads, timestamp hysteresis, idle cleanup."""

from __future__ import annotations

import base64

import cv2
import numpy as np
import pytest
from flask_jwt_extended import create_access_token

from app.db_models import Enrollment, GradeLevel, GuardianConsent, Module, Student, Subject, User
from app.extensions import db
from app.schemas.session_schema import MAX_FRAMES_PER_HEARTBEAT
from app.services.ml_service import RULE_PROXY_THRESHOLD, MLService
from models.src.features.face_pose import FrameFeatures
from models.src.features.windows import WINDOW_FEATURE_NAMES


def _seed(app, email, role="student", consent=True):
    with app.app_context():
        gl = GradeLevel(name=f"G-{email}")
        db.session.add(gl)
        db.session.flush()
        subject = Subject(title="S", grade_level_id=gl.id)
        db.session.add(subject)
        db.session.flush()
        module = Module(title="M", subject_id=subject.id, sequence_order=1)
        db.session.add(module)
        db.session.flush()
        u = User(email=email, password="hash", role=role, first_name="A", last_name="B")
        db.session.add(u)
        db.session.flush()
        if role == "student":
            st = Student(user_id=u.id, grade_level="G")
            db.session.add(st)
            db.session.flush()
            db.session.add(Enrollment(student_id=st.id, subject_id=subject.id))
            if consent:
                db.session.add(
                    GuardianConsent(
                        student_id=st.id,
                        guardian_name="P",
                        guardian_email="p@test.com",
                        consent_given=True,
                    )
                )
        db.session.commit()
        token = create_access_token(identity=str(u.id), additional_claims={"role": role})
        return {"mod_id": module.id, "token": token}


def _start(client, seeded, monitored=True):
    res = client.post(
        "/api/session/start",
        json={"module_id": seeded["mod_id"], "is_monitored": monitored},
        headers={"Authorization": f"Bearer {seeded['token']}"},
    )
    assert res.status_code == 201, res.json
    return res.json["session_id"]


def _gray_jpeg():
    frame = np.full((240, 320, 3), 40, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def _feats(**over):
    base = {name: 0.0 for name in WINDOW_FEATURE_NAMES}
    base.update(
        on_screen_ratio=1.0,
        face_present_ratio=1.0,
        body_present_ratio=1.0,
        window_start_sec=0.0,
        window_sec=5.0,
        baseline_locked=True,
        n_frames=10,
    )
    base.update(over)
    return base


def _frame(face=True):
    return FrameFeatures(
        t_sec=0.0, face_present=face, yaw=0, pitch=0, roll=0, iris_x=0.5, iris_y=0.5,
        blink=0, jaw_open=0, hand_to_face=1, body_motion=0, nose_x=0.5, nose_y=0.4,
        body_present=True,
    )


@pytest.fixture
def svc():
    MLService._instance = None
    s = MLService()
    yield s
    # Close live scorers explicitly: a leaked FaceLandmarker can deadlock in
    # __del__ (GC) during a later test.
    s.shutdown()
    MLService._instance = None


# --- client-supplied features --------------------------------------------------


def test_features_rejected_outside_testing(client, app):
    seeded = _seed(app, "feat_bypass@test.com")
    sid = _start(client, seeded)
    app.config["TESTING"] = False
    try:
        res = client.post(
            f"/api/session/{sid}/heartbeat",
            json={"features": {"gaze_confidence": 0.99, "engagement_score": 1.0}},
            headers={"Authorization": f"Bearer {seeded['token']}"},
        )
    finally:
        app.config["TESTING"] = True
    assert res.status_code == 400


def test_predict_window_features_never_invents_confidence(svc):
    assert svc.predict_window_features({"gaze_confidence": 0.99, "engagement_score": 1.0}) == ("FOCUSED", None)
    assert svc.predict_window_features({"garbage": 1}) == ("UNKNOWN", None)


# --- payload limits ------------------------------------------------------------


def test_oversized_heartbeat_is_413(client, app):
    seeded = _seed(app, "big_hb@test.com")
    sid = _start(client, seeded)
    res = client.post(
        f"/api/session/{sid}/heartbeat",
        data=b'{"image": "' + b"A" * (3 * 1024 * 1024) + b'"}',
        content_type="application/json",
        headers={"Authorization": f"Bearer {seeded['token']}"},
    )
    assert res.status_code == 413


def test_too_many_frames_rejected(client, app):
    seeded = _seed(app, "many_frames@test.com")
    sid = _start(client, seeded)
    img = _gray_jpeg()
    res = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"frames": [{"t_ms": i * 333, "image": img} for i in range(MAX_FRAMES_PER_HEARTBEAT + 1)]},
        headers={"Authorization": f"Bearer {seeded['token']}"},
    )
    assert res.status_code == 400


# --- frames path end to end ----------------------------------------------------


def test_frames_heartbeat_without_face_is_unknown(client, app):
    seeded = _seed(app, "frames_noface@test.com")
    sid = _start(client, seeded)
    img = _gray_jpeg()
    res = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"frames": [{"t_ms": i * 500, "image": img} for i in range(4)]},
        headers={"Authorization": f"Bearer {seeded['token']}"},
    )
    assert res.status_code == 200, res.json
    assert res.json["verdict"] == "UNKNOWN"
    assert res.json["confidence"] is None


def test_unmonitored_session_runs_no_inference(client, app, monkeypatch):
    seeded = _seed(app, "unmonitored@test.com")
    sid = _start(client, seeded, monitored=False)

    def _boom(*_a, **_k):
        raise AssertionError("ML must not run for unmonitored sessions")

    monkeypatch.setattr(MLService, "predict_frames", _boom)
    monkeypatch.setattr(MLService, "predict_frame_image", _boom)
    res = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"image": _gray_jpeg()},
        headers={"Authorization": f"Bearer {seeded['token']}"},
    )
    assert res.status_code == 200
    assert res.json["verdict"] == "UNKNOWN"


# --- decision logic ------------------------------------------------------------


def test_rule_mode_without_v3_pack_uses_measured_score(svc):
    svc.fusion_model = None
    verdict, conf, meta = svc._decide_live("rule-1", _feats(), _frame())
    assert meta["inference_path"] == "rule_proxy"
    assert meta["distract_prob"] < RULE_PROXY_THRESHOLD
    assert verdict == "FOCUSED"
    assert conf == pytest.approx(1.0 - meta["distract_prob"])
    assert conf not in (0.88, 0.90, 0.92)


def test_body_without_face_is_rule_not_model(svc):
    # body_no_face: p=0.7 goes through the hysteresis (no instant DISTRACTED)
    def _step(end):
        return svc._decide_live(
            "body-1",
            _feats(
                face_present_ratio=0.0,
                body_present_ratio=1.0,
                window_start_sec=end - 5.0,
                window_end_sec=end,
            ),
            _frame(face=False),
        )

    verdict, conf, meta = _step(10.0)
    assert verdict == "FOCUSED"
    assert meta["inference_path"] == "rule_body_no_face"
    verdict, conf, meta = _step(13.5)
    assert verdict == "DISTRACTED"
    assert meta["source"] == "body_no_face"
    assert conf == pytest.approx(0.7)


def test_nobody_is_unknown(svc):
    verdict, conf, meta = svc._decide_live(
        "nobody-1", _feats(face_present_ratio=0.0, body_present_ratio=0.0), _frame(face=False)
    )
    assert verdict == "UNKNOWN" and conf is None and meta["reason"] == "no_face"


def test_hysteresis_uses_frame_timestamps(svc):
    params = {"enter_prob": 0.6, "enter_sec": 3.0, "exit_prob": 0.4, "exit_sec": 2.0}
    sid = "hyst-ts"
    assert svc._apply_hysteresis(sid, 0.9, now=10.0, params=params) == "FOCUSED"
    assert svc._apply_hysteresis(sid, 0.1, now=11.0, params=params) == "FOCUSED"  # glance
    assert svc._apply_hysteresis(sid, 0.9, now=12.0, params=params) == "FOCUSED"
    assert svc._apply_hysteresis(sid, 0.9, now=15.0, params=params) == "DISTRACTED"
    assert svc._apply_hysteresis(sid, 0.1, now=16.0, params=params) == "DISTRACTED"
    assert svc._apply_hysteresis(sid, 0.1, now=18.0, params=params) == "FOCUSED"


def test_threshold_env_override_needs_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("ML_FUSION_THRESHOLD", "0.99")
    monkeypatch.delenv("ML_ALLOW_THRESHOLD_OVERRIDE", raising=False)
    MLService._instance = None
    svc = MLService()
    assert svc.fusion_threshold != 0.99
    MLService._instance = None


def test_idle_sessions_are_reaped(svc):
    class _Scorer:
        closed = False

        def close(self):
            _Scorer.closed = True

    svc._live_scorers["idle-1"] = _Scorer()
    svc._session_last_seen["idle-1"] = 0.0
    reaped = svc.reap_idle_sessions(now=svc.session_idle_sec + 1.0)
    assert "idle-1" in reaped
    assert "idle-1" not in svc._live_scorers
    assert _Scorer.closed


# --- Socket.IO -----------------------------------------------------------------


def test_socket_connect_rejects_non_student(app):
    from app.extensions import socketio

    seeded = _seed(app, "teacher_sock@test.com", role="teacher")
    client = socketio.test_client(app, auth={"token": seeded["token"]})
    assert not client.is_connected()


# --- PLAN 5: screen-gaze dwell rule ----------------------------------------------


def _gaze(off=True, dwell=0.0, on_dwell=0.0, ratio=None, calibrated=True):
    return {
        "mode": "screen",
        "calibrated": calibrated,
        "sx": 1.4 if off else 0.5,
        "sy": 0.5,
        "on_screen": not off,
        "off_dwell_sec": dwell if off else 0.0,
        "on_dwell_sec": 0.0 if off else on_dwell,
        "off_ratio": (1.0 if off else 0.0) if ratio is None else ratio,
    }


def test_gaze_dwell_marks_distracted_immediately(svc):
    svc.fusion_model = None  # rule path; the model alone says FOCUSED
    feats = _feats(gaze=_gaze(off=True, dwell=2.4), window_end_sec=100.0, window_start_sec=97.0)
    verdict, conf, meta = svc._decide_live("gaze-1", feats, _frame())
    assert verdict == "DISTRACTED"  # no 3 s enter hold
    assert meta["source"] == "gaze_screen"
    dbg = meta["gaze_debug"]
    assert dbg["p_gaze"] == pytest.approx(0.9)
    assert dbg["p_model"] < dbg["p_gaze"]
    assert dbg["on_screen"] is False and dbg["off_dwell_sec"] == pytest.approx(2.4)
    assert dbg["calibrated"] is True and dbg["source"] == "gaze_screen"
    assert conf == pytest.approx(0.9)


def test_gaze_below_dwell_does_not_fire(svc):
    svc.fusion_model = None
    svc.gaze_offscreen_sec = 2.0
    feats = _feats(gaze=_gaze(off=True, dwell=1.2), window_end_sec=100.0, window_start_sec=97.0)
    verdict, _conf, meta = svc._decide_live("gaze-2", feats, _frame())
    assert verdict == "FOCUSED"
    assert meta["source"] != "gaze_screen"
    assert 0.0 < meta["gaze_debug"]["p_gaze"] < 0.6


def test_gaze_dwell_env_threshold(monkeypatch):
    monkeypatch.setenv("ML_GAZE_OFFSCREEN_SEC", "3.5")
    MLService._instance = None
    s = MLService()
    try:
        assert s.gaze_offscreen_sec == pytest.approx(3.5)
        s.fusion_model = None
        feats = _feats(gaze=_gaze(off=True, dwell=3.0), window_end_sec=10.0, window_start_sec=7.0)
        verdict, _c, _m = s._decide_live("gaze-env", feats, _frame())
        assert verdict == "FOCUSED"
    finally:
        MLService._instance = None


def test_gaze_exit_needs_two_seconds_on_screen(svc):
    svc.fusion_model = None
    sid = "gaze-exit"
    feats = _feats(gaze=_gaze(off=True, dwell=2.5), window_end_sec=100.0, window_start_sec=97.0)
    assert svc._decide_live(sid, feats, _frame())[0] == "DISTRACTED"
    # Looking back, on-screen only 0.6 s: still DISTRACTED
    feats = _feats(gaze=_gaze(off=False, on_dwell=0.6), window_end_sec=101.0, window_start_sec=98.0)
    assert svc._decide_live(sid, feats, _frame())[0] == "DISTRACTED"
    feats = _feats(gaze=_gaze(off=False, on_dwell=1.5), window_end_sec=102.0, window_start_sec=99.0)
    assert svc._decide_live(sid, feats, _frame())[0] == "DISTRACTED"
    # On-screen >= 2 s and the exit hold elapsed -> FOCUSED
    feats = _feats(gaze=_gaze(off=False, on_dwell=2.5), window_end_sec=104.5, window_start_sec=101.5)
    assert svc._decide_live(sid, feats, _frame())[0] == "FOCUSED"


def test_body_no_face_off_screen_dwell_uses_gaze_source(svc):
    feats = _feats(
        face_present_ratio=0.0,
        body_present_ratio=1.0,
        gaze=_gaze(off=True, dwell=2.2),
        window_end_sec=50.0,
        window_start_sec=47.0,
    )
    verdict, _c, meta = svc._decide_live("gaze-body", feats, _frame(face=False))
    assert verdict == "DISTRACTED"
    assert meta["source"] == "gaze_screen"
    assert meta["gaze_debug"]["p_gaze"] == pytest.approx(0.9)


def test_hysteresis_gap_reset_is_six_seconds(svc):
    params = {"enter_prob": 0.6, "enter_sec": 3.0, "exit_prob": 0.4, "exit_sec": 2.0}
    sid = "hyst-gap"
    svc._apply_hysteresis(sid, 0.9, now=10.0, params=params)
    # 5 s gap (> old 4 s limit, < new 6 s): timer survives -> enters DISTRACTED
    assert svc._apply_hysteresis(sid, 0.9, now=15.0, params=params) == "DISTRACTED"
    sid = "hyst-gap2"
    svc._apply_hysteresis(sid, 0.9, now=10.0, params=params)
    assert svc._apply_hysteresis(sid, 0.9, now=17.0, params=params) == "FOCUSED"  # reset


def test_heartbeat_forwards_calibration_and_returns_gaze_debug(client, app, monkeypatch):
    seeded = _seed(app, "calib_fwd@test.com")
    sid = _start(client, seeded)
    seen = {}

    def _fake(self, frames, session_id=None, calibration_phase=None, screen=None):
        seen["frames"] = frames
        seen["phase"] = calibration_phase
        seen["screen"] = screen
        return "UNKNOWN", None, {
            "reason": "calibrating",
            "ml_mode": "full",
            "gaze_debug": {"on_screen": None, "p_gaze": 0.0},
            "calibration": {"phase": calibration_phase, "ok": None},
        }

    monkeypatch.setattr(MLService, "predict_frames", _fake)
    img = _gray_jpeg()
    res = client.post(
        f"/api/session/{sid}/heartbeat",
        json={
            "frames": [
                {"t_ms": 0, "image": img, "calib_target": {"x": 0.5, "y": 0.5}},
                {"t_ms": 333, "image": img},
            ],
            "screen": {"w": 1920, "h": 1080, "inner_w": 1920, "inner_h": 1080, "dpr": 1.25},
            "calibration_phase": "collect",
        },
        headers={"Authorization": f"Bearer {seeded['token']}"},
    )
    assert res.status_code == 200, res.json
    assert seen["phase"] == "collect"
    assert seen["screen"]["w"] == 1920 and seen["screen"]["dpr"] == 1.25
    assert seen["frames"][0][2] == {"x": 0.5, "y": 0.5}
    assert len(seen["frames"][1]) == 2
    assert res.json["gaze_debug"]["p_gaze"] == 0.0
    assert res.json["calibration"]["phase"] == "collect"


def test_invalid_calibration_phase_rejected(client, app):
    seeded = _seed(app, "calib_bad@test.com")
    sid = _start(client, seeded)
    res = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"frames": [{"t_ms": 0, "image": _gray_jpeg()}], "calibration_phase": "bogus"},
        headers={"Authorization": f"Bearer {seeded['token']}"},
    )
    assert res.status_code == 400


# --- PLAN 5 Step 0: model6 pickle drift (_cal) ------------------------------------


def _tiny_pack(n=14):
    import torch

    from models.src.model6_natural.wrapper import FusionMLP

    return {
        "features": [f"f{i}" for i in range(n)],
        "threshold": 0.5,
        "scaler_mean": np.zeros(n),
        "scaler_scale": np.ones(n),
        "state_dict": FusionMLP(n_in=n, hidden=64).state_dict(),
        "hidden": 64,
    }


def test_wrapper_pickled_without_cal_still_predicts():
    import pickle

    from models.src.model6_natural.wrapper import Model6SklearnWrapper

    w = Model6SklearnWrapper(_tiny_pack())
    state = dict(w.__dict__)
    # Simulate a pack pickled by an older class: no _cal / _model / _device / hidden.
    for k in ("_cal", "_model", "_device", "hidden"):
        state.pop(k, None)
    old = Model6SklearnWrapper.__new__(Model6SklearnWrapper)
    old.__dict__.update(state)
    restored = pickle.loads(pickle.dumps(old))
    assert restored._cal is None
    proba = restored.predict_proba(np.zeros((1, 14), dtype=np.float32))
    assert proba.shape == (1, 2)
    assert float(proba.sum()) == pytest.approx(1.0, abs=1e-5)


def test_real_model6_v3_pack_predicts_on_zero_vector():
    from pathlib import Path

    import joblib

    path = (
        Path(__file__).resolve().parents[2]
        / "models" / "outputs" / "checkpoints" / "model6_v3" / "model.pkl"
    )
    if not path.exists():
        pytest.skip("model6_v3 checkpoint not present")
    pack = joblib.load(path)
    model = pack["model"] if isinstance(pack, dict) and "model" in pack else pack
    proba = model.predict_proba(np.zeros((1, 14), dtype=np.float32))
    assert proba.shape == (1, 2)
    assert np.all(np.isfinite(proba))