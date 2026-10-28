import base64
from datetime import datetime, timedelta

import cv2
import numpy as np
import pytest
from flask_jwt_extended import create_access_token

from app.db_models import (
    User,
    Student,
    GradeLevel,
    Subject,
    Module,
    Enrollment,
    GuardianConsent,
    DistractionEvent,
    InterventionLog,
    SystemSetting,
)
from app.extensions import db
from app.routes import session as session_routes


def _seed_student_session(app, email="st_session@test.com"):
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
        existing = SystemSetting.query.filter_by(key="intervention_min_cooldown_seconds").first()
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


def test_session_lifecycle_and_telemetry(client, app):
    seeded = _seed_student_session(app)
    headers = {"Authorization": f"Bearer {seeded['token']}"}

    res_start = client.post(
        "/api/session/start",
        json={"module_id": seeded["mod_id"], "is_monitored": True},
        headers=headers,
    )
    assert res_start.status_code == 201
    session_id = res_start.json["session_id"]

    # Open distracted episode (too short to intervene yet)
    res_open = client.post(
        f"/api/session/{session_id}/heartbeat",
        json={"verdict": "DISTRACTED", "confidence": 0.9},
        headers=headers,
    )
    assert res_open.status_code == 200
    assert res_open.json["intervention_triggered"] is False

    # Backdate open episode into mild band (5–10s) → Tier 1 ambient_cue
    with app.app_context():
        ev = DistractionEvent.query.filter_by(session_id=session_id, ended_at=None).first()
        assert ev is not None
        ev.started_at = datetime.utcnow() - timedelta(seconds=7)
        db.session.commit()

    # Engine may still be pending from nothing; ensure cooldown 0 and no pending
    with app.app_context():
        eng = session_routes.SESSION_ENGINES.get(session_id)
        if eng:
            eng.cooldown_seconds = 0.0
            eng._pending_intervention = False
            eng.last_intervention_at = 0.0

    res_t1 = client.post(
        f"/api/session/{session_id}/heartbeat",
        json={"verdict": "DISTRACTED", "confidence": 0.91},
        headers=headers,
    )
    assert res_t1.status_code == 200
    assert res_t1.json["intervention_triggered"] is True
    assert res_t1.json["intervention"]["tier"] == 1
    assert res_t1.json["intervention"]["intervention_type"] == "ambient_cue"
    intervention_id = res_t1.json["intervention"]["intervention_id"]

    res_resp = client.post(
        f"/api/session/{session_id}/intervention-response",
        json={"intervention_id": intervention_id, "user_response": "reengaged"},
        headers=headers,
    )
    assert res_resp.status_code == 200
    assert res_resp.json["user_response"] == "reengaged"

    # Close episode
    client.post(
        f"/api/session/{session_id}/heartbeat",
        json={"verdict": "FOCUSED", "confidence": 0.95},
        headers=headers,
    )

    res_stop = client.post(f"/api/session/{session_id}/stop", headers=headers)
    assert res_stop.status_code == 200
    assert res_stop.json["total_events"] >= 1
    assert res_stop.json["total_interventions"] == 1


def test_monitored_session_requires_consent(client, app):
    with app.app_context():
        gl = GradeLevel(name="Grade 11")
        db.session.add(gl)
        db.session.flush()

        subject = Subject(title="Chemistry 101", grade_level_id=gl.id)
        db.session.add(subject)
        db.session.flush()

        module = Module(title="Atoms", subject_id=subject.id, sequence_order=1)
        db.session.add(module)
        db.session.flush()

        st_u = User(
            email="noconsent@test.com",
            password="hash",
            role="student",
            first_name="No",
            last_name="Consent",
        )
        db.session.add(st_u)
        db.session.flush()

        student = Student(user_id=st_u.id, grade_level="Grade 11")
        db.session.add(student)
        db.session.flush()

        db.session.add(Enrollment(student_id=student.id, subject_id=subject.id))
        db.session.commit()

        mod_id = module.id
        st_token = create_access_token(
            identity=str(st_u.id), additional_claims={"role": "student"}
        )

    headers = {"Authorization": f"Bearer {st_token}"}

    res_no_consent = client.post(
        "/api/session/start",
        json={"module_id": mod_id, "is_monitored": True},
        headers=headers,
    )
    assert res_no_consent.status_code == 403
    assert "consent required" in res_no_consent.json["error"].lower()

    res_unmonitored = client.post(
        "/api/session/start",
        json={"module_id": mod_id, "is_monitored": False},
        headers=headers,
    )
    assert res_unmonitored.status_code == 201


def test_heartbeat_with_image_returns_ml_verdict(client, app):
    seeded = _seed_student_session(app, email="ml_frame@test.com")
    headers = {"Authorization": f"Bearer {seeded['token']}"}

    res_start = client.post(
        "/api/session/start",
        json={"module_id": seeded["mod_id"], "is_monitored": True},
        headers=headers,
    )
    assert res_start.status_code == 201
    session_id = res_start.json["session_id"]

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = (30, 30, 30)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    image_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()

    res = client.post(
        f"/api/session/{session_id}/heartbeat",
        json={"image": image_b64, "verdict": "FOCUSED", "confidence": 0.99},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json
    # Decoded blank frame → no face → UNKNOWN (not DISTRACTED)
    assert body["verdict"] == "UNKNOWN"
    assert body["confidence"] is None
    assert body["reason"] == "no_face"
    assert body["face_detected"] is False
    assert body["ml_mode"] in ("full", "partial", "fallback")
    assert "intervention_triggered" in body
    assert body["intervention_triggered"] is False


def test_sustained_background_noise_triggers_one_time_notice(client, app):
    seeded = _seed_student_session(app, email="noise_trigger@test.com")
    headers = {"Authorization": f"Bearer {seeded['token']}"}

    res_start = client.post(
        "/api/session/start",
        json={"module_id": seeded["mod_id"], "is_monitored": True},
        headers=headers,
    )
    assert res_start.status_code == 201
    session_id = res_start.json["session_id"]

    def heartbeat(noise_dbfs, lesson_audio_active=False):
        return client.post(
            f"/api/session/{session_id}/heartbeat",
            json={
                "verdict": "FOCUSED",
                "confidence": 0.95,
                "noise_dbfs": noise_dbfs,
                "lesson_audio_active": lesson_audio_active,
            },
            headers=headers,
        )

    # Calibration beats (quiet room), including one lesson-audio sample that
    # must not pollute the baseline.
    assert heartbeat(-10.0, lesson_audio_active=True).json["noise_baseline_dbfs"] is None
    for _ in range(5):
        res = heartbeat(-50.0)
        assert res.status_code == 200
        assert res.json["noise_triggered"] is False
    assert res.json["noise_baseline_dbfs"] == -50.0

    # Sustained loud room (+20 dB): only the 4th beat fires.
    for _ in range(3):
        res = heartbeat(-30.0)
        assert res.json["noise_triggered"] is False
        assert res.json["intervention_triggered"] is False
    res = heartbeat(-30.0)
    assert res.status_code == 200
    assert res.json["noise_triggered"] is True
    assert res.json["verdict"] == "FOCUSED"  # noise never flips the ML verdict
    assert res.json["intervention"]["tier"] == 1
    assert res.json["intervention"]["intervention_type"] == "environment_noise_notice"
    assert res.json["intervention"]["payload"]["trigger_source"] == "background_noise"
    intervention_id = res.json["intervention"]["intervention_id"]

    # Noise must not open a distraction episode.
    with app.app_context():
        assert (
            DistractionEvent.query.filter_by(
                session_id=session_id, verdict="distracted"
            ).count()
            == 0
        )
        assert session_id in session_routes.SESSION_NOISE_MONITORS
        assert session_routes.SESSION_NOISE_MONITORS[session_id].notice_shown is True

    # Student picks a fix; the choice is logged on the intervention.
    res_resp = client.post(
        f"/api/session/{session_id}/intervention-response",
        json={
            "intervention_id": intervention_id,
            "user_response": "reengaged",
            "noise_action": "headphones",
        },
        headers=headers,
    )
    assert res_resp.status_code == 200
    assert res_resp.json["noise_action"] == "headphones"
    with app.app_context():
        log = db.session.get(InterventionLog, intervention_id)
        assert log.noise_action == "headphones"
        assert log.intervention_type == "environment_noise_notice"

    # One-time per session: another full sustained-loud run fires nothing.
    for _ in range(5):
        res = heartbeat(-30.0)
        assert res.json["noise_triggered"] is False
        assert res.json["intervention_triggered"] is False
    with app.app_context():
        assert (
            InterventionLog.query.filter_by(
                session_id=session_id,
                intervention_type="environment_noise_notice",
            ).count()
            == 1
        )

    client.post(f"/api/session/{session_id}/stop", headers=headers)
    with app.app_context():
        assert session_id not in session_routes.SESSION_NOISE_MONITORS


def test_trigger_milestone_quiz_intervention(client, app):
    seeded = _seed_student_session(app, email="t3_quiz@test.com")
    headers = {"Authorization": f"Bearer {seeded['token']}"}

    res_start = client.post(
        "/api/session/start",
        json={"module_id": seeded["mod_id"], "is_monitored": True},
        headers=headers,
    )
    assert res_start.status_code == 201
    session_id = res_start.json["session_id"]

    res_t3 = client.post(
        f"/api/session/{session_id}/trigger-intervention",
        json={"tier": 3},
        headers=headers,
    )
    assert res_t3.status_code == 200
    data = res_t3.json
    assert data["intervention_triggered"] is True
    assert data["intervention"]["tier"] == 3
    assert data["intervention"]["intervention_type"] == "milestone_quiz"
    assert "milestone_question_id" in data["intervention"]["payload"]


def test_repeated_stop_awards_xp_only_once(client, app):
    """Regression: second POST .../stop must not award XP again."""
    from app.db_models import LearningSession, StudentProgress

    seeded = _seed_student_session(app, email="xp_once@test.com")
    headers = {"Authorization": f"Bearer {seeded['token']}"}

    res_start = client.post(
        "/api/session/start",
        json={"module_id": seeded["mod_id"], "is_monitored": True},
        headers=headers,
    )
    assert res_start.status_code == 201
    session_id = res_start.json["session_id"]

    # Give the session a non-trivial duration so XP > 0
    with app.app_context():
        sess = db.session.get(LearningSession, session_id)
        sess.start_time = datetime.utcnow() - timedelta(minutes=10)
        db.session.commit()

    # Phase 2A: XP from observed focused time only — seed focused observations.
    with app.app_context():
        from app.db_models import MonitoringObservation

        sess = db.session.get(LearningSession, session_id)
        t0 = sess.start_time
        for i in range(0, 600, 2):
            db.session.add(
                MonitoringObservation(
                    session_id=session_id,
                    observed_at=t0 + timedelta(seconds=i),
                    state="FOCUSED",
                    confidence=0.9,
                    face_detected=True,
                    ml_mode="fallback",
                )
            )
        db.session.commit()

    res1 = client.post(f"/api/session/{session_id}/stop", headers=headers)
    assert res1.status_code == 200
    xp_first = res1.json.get("xp_gained", 0)
    assert xp_first > 0
    assert res1.json.get("focus_metric_version") == "observed_v1"
    assert res1.json.get("focus_percentage") is not None

    with app.app_context():
        progress = StudentProgress.query.filter_by(
            student_id=db.session.get(LearningSession, session_id).student_id
        ).first()
        xp_after_first = progress.xp if progress else 0

    res2 = client.post(f"/api/session/{session_id}/stop", headers=headers)
    assert res2.status_code == 200
    assert res2.json.get("xp_gained", 0) == 0

    with app.app_context():
        progress = StudentProgress.query.filter_by(
            student_id=db.session.get(LearningSession, session_id).student_id
        ).first()
        assert progress.xp == xp_after_first


def test_claim_session_xp_award_is_atomic(tmp_path, monkeypatch):
    """
    Concurrent-safe claim: only one caller gets True for the same session.

    Uses a file-backed SQLite DB so worker threads share state (:memory: is
    per-connection and cannot exercise concurrent UPDATE correctly).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from app import create_app
    from app.config import TestingConfig
    from app.db_models import LearningSession, Student, User, GradeLevel, Subject, Module
    from app.routes.session import claim_session_xp_award
    from app.services.ml_service import MLService

    db_file = tmp_path / "xp_claim.db"
    uri = f"sqlite:///{db_file.resolve().as_posix()}?check_same_thread=False"
    monkeypatch.setattr(TestingConfig, "SQLALCHEMY_DATABASE_URI", uri)

    MLService._instance = None
    file_app = create_app("testing")

    with file_app.app_context():
        gl = GradeLevel(name="G-xp-claim")
        db.session.add(gl)
        db.session.flush()
        subject = Subject(title="XP Claim Subject", grade_level_id=gl.id)
        db.session.add(subject)
        db.session.flush()
        module = Module(title="M", subject_id=subject.id, sequence_order=1)
        db.session.add(module)
        db.session.flush()
        u = User(
            email="xp_claim@test.com",
            password="hash",
            role="student",
            first_name="X",
            last_name="P",
        )
        db.session.add(u)
        db.session.flush()
        student = Student(user_id=u.id, grade_level="G-xp-claim")
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

    results = []

    def _claim():
        with file_app.app_context():
            return claim_session_xp_award(session_id)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_claim) for _ in range(8)]
        for fut in as_completed(futures):
            results.append(fut.result())

    assert results.count(True) == 1, results
    assert results.count(False) == 7, results

    with file_app.app_context():
        sess = db.session.get(LearningSession, session_id)
        assert sess.xp_awarded is True

    MLService._instance = None



def test_list_and_stop_active_sessions(client, app):
    """Students can see and stop monitoring left running (e.g. a closed tab)."""
    from app.db_models import LearningSession

    seeded = _seed_student_session(app, email="stop_active@test.com")
    headers = {"Authorization": f"Bearer {seeded['token']}"}

    res_empty = client.get("/api/session/active", headers=headers)
    assert res_empty.status_code == 200
    assert res_empty.json["count"] == 0

    res_start = client.post(
        "/api/session/start",
        json={"module_id": seeded["mod_id"], "is_monitored": True},
        headers=headers,
    )
    session_id = res_start.json["session_id"]

    res_active = client.get("/api/session/active", headers=headers)
    assert res_active.json["count"] == 1
    row = res_active.json["sessions"][0]
    assert row["session_id"] == session_id
    assert row["module_title"] == "Kinematics"
    assert row["subject_title"] == "Physics 101"

    res_stop = client.post("/api/session/stop-active", headers=headers)
    assert res_stop.status_code == 200
    assert res_stop.json["stopped_count"] == 1
    assert res_stop.json["sessions"][0]["session_id"] == session_id
    assert session_id not in session_routes.SESSION_ENGINES

    with app.app_context():
        assert db.session.get(LearningSession, session_id).end_time is not None

    # Nothing left to stop; calling again is harmless
    assert client.get("/api/session/active", headers=headers).json["count"] == 0
    res_again = client.post("/api/session/stop-active", headers=headers)
    assert res_again.status_code == 200
    assert res_again.json["stopped_count"] == 0


def test_stop_active_only_touches_own_sessions(client, app):
    from app.db_models import LearningSession

    a = _seed_student_session(app, email="owner_a@test.com")
    b = _seed_student_session(app, email="owner_b@test.com")
    ha = {"Authorization": f"Bearer {a['token']}"}
    hb = {"Authorization": f"Bearer {b['token']}"}

    sid_a = client.post("/api/session/start", json={"module_id": a["mod_id"], "is_monitored": True}, headers=ha).json["session_id"]
    sid_b = client.post("/api/session/start", json={"module_id": b["mod_id"], "is_monitored": True}, headers=hb).json["session_id"]

    res = client.post("/api/session/stop-active", headers=ha)
    assert res.json["stopped_count"] == 1

    with app.app_context():
        assert db.session.get(LearningSession, sid_a).end_time is not None
        assert db.session.get(LearningSession, sid_b).end_time is None
