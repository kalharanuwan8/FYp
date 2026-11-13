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
        json={"frames": [{"t_ms": i * 500, "image": img} for i in range(7)]},
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
    verdict, conf, meta = svc._decide_live(
        "body-1", _feats(face_present_ratio=0.0, body_present_ratio=1.0), _frame(face=False)
    )
    assert verdict == "DISTRACTED"
    assert conf is None
    assert meta["inference_path"] == "rule_body_no_face"


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
