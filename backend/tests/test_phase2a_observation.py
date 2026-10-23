"""Phase 2A: UNKNOWN observations, coverage accounting, MediaPipe isolation, XP txn."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from app.extensions import db
from app.db_models import (
    LearningSession,
    MonitoringObservation,
    DistractionEvent,
    GradeLevel,
    Subject,
    Module,
    User,
    Student,
)
from app.services.ml_service import MLService
from app.services.intervention_engine import InterventionEngine
from app.services.observation_coverage import (
    ObservationPoint,
    compute_coverage_from_observations,
    FOCUS_METRIC_VERSION,
    T_SUPPORT,
    T_GAP_MAX,
    is_interrupted_monitoring_gap,
)
from app.services.gamification_service import award_session_xp, XP_PER_FOCUS_MINUTE
from app.routes.session import (
    claim_session_xp_award,
    award_claimed_session_xp,
    upsert_distraction_episode,
)


def test_coverage_valid_observations_and_gaps():
    start = datetime(2026, 1, 1, 12, 0, 0)
    end = start + timedelta(seconds=20)
    obs = [
        ObservationPoint(start + timedelta(seconds=0), "FOCUSED"),
        ObservationPoint(start + timedelta(seconds=2), "FOCUSED"),
        ObservationPoint(start + timedelta(seconds=10), "DISTRACTED"),
        ObservationPoint(start + timedelta(seconds=12), "FOCUSED"),
    ]
    cov = compute_coverage_from_observations(
        start_time=start, end_time=end, observations=obs
    )
    assert cov.focus_metric_version == FOCUS_METRIC_VERSION
    assert cov.observed_focused_seconds > 0
    assert cov.observed_distracted_seconds > 0
    assert cov.unknown_seconds > 0
    # Gap from t=2 to t=10 is 8s; only T_SUPPORT credited after last focused
    assert cov.unknown_seconds >= (8.0 - T_SUPPORT) - 0.01
    assert cov.focus_percentage is not None
    assert 0 <= cov.focus_percentage <= 100
    assert abs(
        cov.observed_focused_seconds
        + cov.observed_distracted_seconds
        + cov.unknown_seconds
        - 20.0
    ) < 0.05


def test_coverage_zero_valid_observations_null_focus():
    start = datetime(2026, 1, 1, 12, 0, 0)
    end = start + timedelta(seconds=30)
    obs = [
        ObservationPoint(start + timedelta(seconds=1), "UNKNOWN"),
        ObservationPoint(start + timedelta(seconds=5), "UNKNOWN"),
    ]
    cov = compute_coverage_from_observations(
        start_time=start, end_time=end, observations=obs
    )
    assert cov.focus_percentage is None
    assert cov.observed_focused_seconds == 0
    assert cov.observed_distracted_seconds == 0
    assert cov.monitoring_coverage_pct == 0
    assert cov.unknown_seconds == pytest.approx(30.0)


def test_coverage_unmonitored_empty_session():
    start = datetime(2026, 1, 1, 12, 0, 0)
    end = start + timedelta(seconds=60)
    cov = compute_coverage_from_observations(
        start_time=start, end_time=end, observations=[]
    )
    assert cov.focus_percentage is None
    assert cov.unknown_seconds == pytest.approx(60.0)
    assert cov.monitoring_coverage_pct == 0


def test_coverage_distracted_gap_unknown_remainder():
    """DISTRACTED@0 then DISTRACTED@4 → [3,4) unknown; durations partition session."""
    start = datetime(2026, 1, 1, 12, 0, 0)
    end = start + timedelta(seconds=10)
    obs = [
        ObservationPoint(start + timedelta(seconds=0), "DISTRACTED"),
        ObservationPoint(start + timedelta(seconds=4), "DISTRACTED"),
    ]
    cov = compute_coverage_from_observations(
        start_time=start, end_time=end, observations=obs
    )
    # First covers [0,3); second covers [4, min(4+3,10)] = [4,7)
    assert cov.observed_distracted_seconds == pytest.approx(3.0 + 3.0)
    assert cov.observed_focused_seconds == 0.0
    assert cov.unknown_seconds == pytest.approx(10.0 - 6.0)
    assert abs(
        cov.observed_focused_seconds
        + cov.observed_distracted_seconds
        + cov.unknown_seconds
        - 10.0
    ) < 0.01
    assert 4.0 > T_SUPPORT
    assert 4.0 < T_GAP_MAX  # gap is unknown for coverage even when < T_gap_max
    assert not is_interrupted_monitoring_gap(4.0)
    assert is_interrupted_monitoring_gap(6.0)


def test_coverage_distracted_then_unknown_clips_support():
    """DISTRACTED@0, UNKNOWN@1 → prior support stops at t=1."""
    start = datetime(2026, 1, 1, 12, 0, 0)
    end = start + timedelta(seconds=10)
    obs = [
        ObservationPoint(start + timedelta(seconds=0), "DISTRACTED"),
        ObservationPoint(start + timedelta(seconds=1), "UNKNOWN"),
    ]
    cov = compute_coverage_from_observations(
        start_time=start, end_time=end, observations=obs
    )
    assert cov.observed_distracted_seconds == pytest.approx(1.0)
    assert cov.unknown_seconds == pytest.approx(9.0)


def test_coverage_support_clipped_at_session_end():
    start = datetime(2026, 1, 1, 12, 0, 0)
    end = start + timedelta(seconds=2)
    obs = [ObservationPoint(start + timedelta(seconds=0), "FOCUSED")]
    cov = compute_coverage_from_observations(
        start_time=start, end_time=end, observations=obs
    )
    assert cov.observed_focused_seconds == pytest.approx(2.0)
    assert cov.unknown_seconds == pytest.approx(0.0)


def test_unknown_closes_open_distraction_episode(app):
    with app.app_context():
        gl = GradeLevel(name="G-p2a-ep")
        db.session.add(gl)
        db.session.flush()
        subject = Subject(title="P2A", grade_level_id=gl.id)
        db.session.add(subject)
        db.session.flush()
        module = Module(title="M", subject_id=subject.id, sequence_order=1)
        db.session.add(module)
        db.session.flush()
        u = User(
            email="p2a_ep@test.com",
            password="hash",
            role="student",
            first_name="A",
            last_name="B",
        )
        db.session.add(u)
        db.session.flush()
        student = Student(user_id=u.id, grade_level="G-p2a-ep")
        db.session.add(student)
        db.session.flush()
        sess = LearningSession(
            student_id=student.id, module_id=module.id, is_monitored=True
        )
        db.session.add(sess)
        db.session.commit()
        sid = sess.id
        t0 = datetime.utcnow()

        upsert_distraction_episode(sid, "DISTRACTED", 0.9, t0)
        open_ev = DistractionEvent.query.filter_by(session_id=sid, ended_at=None).first()
        assert open_ev is not None

        upsert_distraction_episode(sid, "UNKNOWN", 0.0, t0 + timedelta(seconds=5))
        open_ev = DistractionEvent.query.filter_by(session_id=sid, ended_at=None).first()
        assert open_ev is None
        closed = DistractionEvent.query.filter_by(session_id=sid).first()
        assert closed.ended_at is not None


def test_predict_invalid_image_is_unknown():
    MLService._instance = None
    svc = MLService()
    verdict, conf, meta = svc.predict_frame_image("not-valid-base64!!!", session_id=1)
    assert verdict == "UNKNOWN"
    assert conf is None
    assert meta.get("face_detected") is None
    assert meta.get("reason") == "no_frame_data"
    MLService._instance = None


def test_predict_exception_is_unknown_not_focused():
    MLService._instance = None
    svc = MLService()
    with patch.object(svc, "_decode_frame", return_value=__import__("numpy").zeros((10, 10, 3), dtype="uint8")):
        with patch.object(svc, "_infer_frame_signals", side_effect=RuntimeError("boom")):
            verdict, conf, meta = svc.predict_frame_image("ignored", session_id=42)
    assert verdict == "UNKNOWN"
    assert conf is None
    assert meta.get("face_detected") is not True
    assert meta.get("reason") == "inference_exception"
    MLService._instance = None


def test_mediapipe_landmarkers_are_session_isolated():
    """Sequential and interleaved sessions must not share a VIDEO landmarker."""
    MLService._instance = None
    svc = MLService()
    fake_a = MagicMock(name="lm_a")
    fake_b = MagicMock(name="lm_b")
    created = []

    def _factory():
        lm = fake_a if len(created) == 0 else fake_b
        created.append(lm)
        return lm

    svc._mp_available = True
    svc._mp_module = MagicMock()
    svc._pose_landmarker_task_path = MagicMock()
    with patch.object(svc, "_create_session_landmarker", side_effect=_factory):
        la = svc._landmarker_for_session("sess-1")
        lb = svc._landmarker_for_session("sess-2")
        la2 = svc._landmarker_for_session("sess-1")
        assert la is fake_a
        assert lb is fake_b
        assert la2 is fake_a
        assert la is not lb

        ts1 = svc._next_landmark_timestamp_ms("sess-1")
        ts2 = svc._next_landmark_timestamp_ms("sess-2")
        ts1b = svc._next_landmark_timestamp_ms("sess-1")
        assert ts1b > ts1
        # Independent counters — sess-2 clock does not need to exceed sess-1
        assert ts2 > 0

        svc.clear_session("sess-1")
        assert "sess-1" not in svc._session_landmarkers
        fake_a.close.assert_called()
        assert "sess-2" in svc._session_landmarkers
        svc.clear_session("sess-2")
        fake_b.close.assert_called()
    MLService._instance = None


def _seed_for_phase2a(app, email):
    """Local copy of session test seed to avoid cross-module import issues."""
    from flask_jwt_extended import create_access_token
    from app.db_models import Enrollment, GuardianConsent, SystemSetting

    with app.app_context():
        gl = GradeLevel(name=f"Grade-{email}")
        db.session.add(gl)
        db.session.flush()
        subject = Subject(title="Physics 101", grade_level_id=gl.id)
        db.session.add(subject)
        db.session.flush()
        module = Module(title="Kinematics", subject_id=subject.id, sequence_order=1)
        db.session.add(module)
        db.session.flush()
        st_u = User(
            email=email, password="hash", role="student", first_name="St", last_name="S"
        )
        db.session.add(st_u)
        db.session.flush()
        student = Student(user_id=st_u.id, grade_level="Grade 10")
        db.session.add(student)
        db.session.flush()
        db.session.add(Enrollment(student_id=student.id, subject_id=subject.id))
        db.session.add(
            GuardianConsent(
                student_id=student.id,
                guardian_name="Parent",
                guardian_email="parent@test.com",
                consent_given=True,
            )
        )
        existing = SystemSetting.query.filter_by(
            key="intervention_min_cooldown_seconds"
        ).first()
        if existing:
            existing.value = "0"
        else:
            db.session.add(
                SystemSetting(key="intervention_min_cooldown_seconds", value="0")
            )
        db.session.commit()
        return {
            "mod_id": module.id,
            "token": create_access_token(
                identity=str(st_u.id), additional_claims={"role": "student"}
            ),
        }


def test_heartbeat_unknown_via_corrupt_image(client, app):
    seeded = _seed_for_phase2a(app, email="p2a_unk@test.com")
    headers = {"Authorization": f"Bearer {seeded['token']}"}
    res_start = client.post(
        "/api/session/start",
        json={"module_id": seeded["mod_id"], "is_monitored": True},
        headers=headers,
    )
    assert res_start.status_code == 201
    sid = res_start.json["session_id"]

    res = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"image": "data:image/jpeg;base64,AAAA", "verdict": "FOCUSED"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json["verdict"] == "UNKNOWN"
    assert res.json["confidence"] is None
    assert res.json.get("face_detected") in (None, False)

    with app.app_context():
        row = MonitoringObservation.query.filter_by(session_id=sid).first()
        assert row is not None
        assert row.state == "UNKNOWN"


def test_stop_zero_coverage_null_focus_no_focus_xp(client, app):
    seeded = _seed_for_phase2a(app, email="p2a_zero@test.com")
    headers = {"Authorization": f"Bearer {seeded['token']}"}
    res_start = client.post(
        "/api/session/start",
        json={"module_id": seeded["mod_id"], "is_monitored": True},
        headers=headers,
    )
    sid = res_start.json["session_id"]
    with app.app_context():
        sess = db.session.get(LearningSession, sid)
        sess.start_time = datetime.utcnow() - timedelta(minutes=5)
        db.session.commit()

    res = client.post(f"/api/session/{sid}/stop", headers=headers)
    assert res.status_code == 200
    assert res.json["focus_percentage"] is None
    assert res.json["monitoring_coverage_pct"] == 0
    assert res.json["xp_gained"] == 0
    assert res.json["focus_metric_version"] == FOCUS_METRIC_VERSION


def test_xp_claim_and_award_rollback_then_retry(tmp_path, monkeypatch, app):
    """If reward update fails after claim, claim rolls back and retry can succeed."""
    from app.config import TestingConfig
    from app import create_app

    db_file = tmp_path / "xp_txn.db"
    uri = f"sqlite:///{db_file.resolve().as_posix()}?check_same_thread=False"
    monkeypatch.setattr(TestingConfig, "SQLALCHEMY_DATABASE_URI", uri)
    MLService._instance = None
    file_app = create_app("testing")

    with file_app.app_context():
        gl = GradeLevel(name="G-xp-txn")
        db.session.add(gl)
        db.session.flush()
        subject = Subject(title="XP Txn", grade_level_id=gl.id)
        db.session.add(subject)
        db.session.flush()
        module = Module(title="M", subject_id=subject.id, sequence_order=1)
        db.session.add(module)
        db.session.flush()
        u = User(
            email="xp_txn@test.com",
            password="hash",
            role="student",
            first_name="X",
            last_name="T",
        )
        db.session.add(u)
        db.session.flush()
        student = Student(user_id=u.id, grade_level="G-xp-txn")
        db.session.add(student)
        db.session.flush()
        sess = LearningSession(
            student_id=student.id,
            module_id=module.id,
            is_monitored=True,
            xp_awarded=False,
        )
        db.session.add(sess)
        db.session.commit()
        session_id = sess.id
        student_id = student.id

    with file_app.app_context():
        with patch(
            "app.services.gamification_service.award_session_xp",
            side_effect=RuntimeError("simulated award failure"),
        ):
            # First attempt fails inside award_claimed — claim must roll back
            out1 = award_claimed_session_xp(
                session_id=session_id,
                student_id=student_id,
                observed_focused_seconds=120.0,
                max_retries=0,
            )
            assert out1.get("xp_gained", 0) == 0
            sess = db.session.get(LearningSession, session_id)
            assert sess.xp_awarded is False

        out2 = award_claimed_session_xp(
            session_id=session_id,
            student_id=student_id,
            observed_focused_seconds=120.0,
        )
        assert out2["xp_gained"] > 0
        sess = db.session.get(LearningSession, session_id)
        assert sess.xp_awarded is True

    MLService._instance = None


def test_claim_session_xp_award_commit_false_stays_uncommitted_until_outer(app):
    with app.app_context():
        gl = GradeLevel(name="G-claim-nc")
        db.session.add(gl)
        db.session.flush()
        subject = Subject(title="Claim NC", grade_level_id=gl.id)
        db.session.add(subject)
        db.session.flush()
        module = Module(title="M", subject_id=subject.id, sequence_order=1)
        db.session.add(module)
        db.session.flush()
        u = User(
            email="claim_nc@test.com",
            password="hash",
            role="student",
            first_name="C",
            last_name="N",
        )
        db.session.add(u)
        db.session.flush()
        student = Student(user_id=u.id, grade_level="G-claim-nc")
        db.session.add(student)
        db.session.flush()
        sess = LearningSession(
            student_id=student.id, module_id=module.id, xp_awarded=False
        )
        db.session.add(sess)
        db.session.commit()
        sid = sess.id

        ok = claim_session_xp_award(sid, commit=False)
        assert ok is True
        db.session.rollback()
        sess = db.session.get(LearningSession, sid)
        assert sess.xp_awarded is False


def test_predict_no_face_is_unknown_with_face_detected_false():
    MLService._instance = None
    svc = MLService()
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = (40, 40, 40)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    image_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()
    verdict, conf, meta = svc.predict_frame_image(image_b64, session_id="noface-1")
    assert verdict == "UNKNOWN"
    assert conf is None
    assert meta.get("reason") == "no_face"
    assert meta.get("face_detected") is False
    MLService._instance = None


def test_episode_gap_breaks_continuity_for_intervention(app):
    """DISTRACTED@0 then DISTRACTED@4 closes prior at +T_SUPPORT and opens new."""
    with app.app_context():
        gl = GradeLevel(name="G-p2a-gap")
        db.session.add(gl)
        db.session.flush()
        subject = Subject(title="Gap", grade_level_id=gl.id)
        db.session.add(subject)
        db.session.flush()
        module = Module(title="M", subject_id=subject.id, sequence_order=1)
        db.session.add(module)
        db.session.flush()
        u = User(
            email="p2a_gap@test.com",
            password="hash",
            role="student",
            first_name="A",
            last_name="B",
        )
        db.session.add(u)
        db.session.flush()
        student = Student(user_id=u.id, grade_level="G-p2a-gap")
        db.session.add(student)
        db.session.flush()
        sess = LearningSession(
            student_id=student.id, module_id=module.id, is_monitored=True
        )
        db.session.add(sess)
        db.session.commit()
        sid = sess.id
        t0 = datetime(2026, 1, 1, 12, 0, 0)

        db.session.add(
            MonitoringObservation(
                session_id=sid,
                observed_at=t0,
                state="DISTRACTED",
                confidence=0.9,
            )
        )
        db.session.commit()
        ev1, _ = upsert_distraction_episode(sid, "DISTRACTED", 0.9, t0)
        assert ev1 is not None
        assert ev1.ended_at is None

        t4 = t0 + timedelta(seconds=4)
        db.session.add(
            MonitoringObservation(
                session_id=sid,
                observed_at=t4,
                state="DISTRACTED",
                confidence=0.9,
            )
        )
        db.session.commit()
        ev2, _ = upsert_distraction_episode(sid, "DISTRACTED", 0.9, t4)
        assert ev2 is not None
        assert ev2.id != ev1.id
        db.session.refresh(ev1)
        assert ev1.ended_at == t0 + timedelta(seconds=T_SUPPORT)
        assert ev2.started_at == t4
        assert ev2.ended_at is None
        # New episode duration at t4+1 must not include the [3,4) unknown gap
        assert ev2.duration_seconds(t4 + timedelta(seconds=1)) == pytest.approx(1.0)


def test_unknown_does_not_reset_pending_intervention():
    engine = InterventionEngine(cooldown_seconds=30.0)
    class _Ep:
        def duration_seconds(self, now=None):
            return 8.0

    triggered = engine.decide_intervention(
        distraction_event=_Ep(),
        is_distracted=True,
        observation_state="DISTRACTED",
        now=100.0,
    )
    assert triggered is not None
    assert engine._pending_intervention is True
    last_tier = engine.last_tier
    last_at = engine.last_intervention_at

    assert (
        engine.decide_intervention(
            distraction_event=None,
            is_distracted=False,
            observation_state="UNKNOWN",
            now=105.0,
        )
        is None
    )
    assert engine._pending_intervention is True
    assert engine.last_tier == last_tier
    assert engine.last_intervention_at == last_at

    # FOCUSED still resets
    assert (
        engine.decide_intervention(
            distraction_event=None,
            is_distracted=False,
            observation_state="FOCUSED",
            now=110.0,
        )
        is None
    )
    assert engine._pending_intervention is False
    assert engine.last_tier is None


def test_zero_observed_focused_awards_zero_session_xp(app):
    with app.app_context():
        gl = GradeLevel(name="G-p2a-zxp")
        db.session.add(gl)
        db.session.flush()
        subject = Subject(title="ZXP", grade_level_id=gl.id)
        db.session.add(subject)
        db.session.flush()
        module = Module(title="M", subject_id=subject.id, sequence_order=1)
        db.session.add(module)
        db.session.flush()
        u = User(
            email="p2a_zxp@test.com",
            password="hash",
            role="student",
            first_name="Z",
            last_name="X",
        )
        db.session.add(u)
        db.session.flush()
        student = Student(user_id=u.id, grade_level="G-p2a-zxp")
        db.session.add(student)
        db.session.commit()

        # Long wall-clock session, zero observed focus → no focus XP (no minimum award)
        result = award_session_xp(
            student.id,
            duration_seconds=3600,
            focus_percentage=None,
            observed_focused_seconds=0.0,
        )
        assert result["xp_gained"] == 0
        assert result["focus_minutes"] == 0
        assert XP_PER_FOCUS_MINUTE > 0


def test_start_clears_prior_session_landmarker(client, app):
    seeded = _seed_for_phase2a(app, email="p2a_lm_cleanup@test.com")
    headers = {"Authorization": f"Bearer {seeded['token']}"}
    MLService._instance = None
    svc = MLService()
    fake = MagicMock(name="lm_prior")
    with patch.object(svc, "_create_session_landmarker", return_value=fake):
        res1 = client.post(
            "/api/session/start",
            json={"module_id": seeded["mod_id"], "is_monitored": True},
            headers=headers,
        )
        sid1 = res1.json["session_id"]
        # Attach a landmarker as if heartbeats ran
        MLService._instance = svc
        svc._landmarker_for_session(sid1)
        assert sid1 in svc._session_landmarkers

        res2 = client.post(
            "/api/session/start",
            json={"module_id": seeded["mod_id"], "is_monitored": True},
            headers=headers,
        )
        assert res2.status_code == 201
        sid2 = res2.json["session_id"]
        assert sid1 != sid2
        assert sid1 not in svc._session_landmarkers
        fake.close.assert_called()
    MLService._instance = None


def test_heartbeat_no_face_persists_unknown(client, app):
    seeded = _seed_for_phase2a(app, email="p2a_noface_hb@test.com")
    headers = {"Authorization": f"Bearer {seeded['token']}"}
    res_start = client.post(
        "/api/session/start",
        json={"module_id": seeded["mod_id"], "is_monitored": True},
        headers=headers,
    )
    sid = res_start.json["session_id"]
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    image_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()
    res = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"image": image_b64},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json["verdict"] == "UNKNOWN"
    assert res.json["reason"] == "no_face"
    assert res.json["confidence"] is None
    assert res.json["face_detected"] is False
    with app.app_context():
        row = MonitoringObservation.query.filter_by(session_id=sid).first()
        assert row.state == "UNKNOWN"
        assert row.face_detected is False
        assert row.confidence is None
        open_ev = DistractionEvent.query.filter_by(
            session_id=sid, ended_at=None
        ).first()
        assert open_ev is None
