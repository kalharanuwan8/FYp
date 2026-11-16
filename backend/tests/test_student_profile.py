import pytest
from flask_jwt_extended import create_access_token
from app.db_models import User, Student, GuardianConsent, GradeLevel
from app.extensions import db


def test_student_profile_lifecycle(client, app):
    with app.app_context():
        # Setup Grade Level
        gl = GradeLevel(name="Grade 6")
        db.session.add(gl)
        db.session.commit()

        # Create student user
        u = User(
            email="student_prof@test.com",
            password="hashedpassword",
            role="student",
            first_name="Alex",
            last_name="Smith"
        )
        db.session.add(u)
        db.session.flush()

        st = Student(user_id=u.id, grade_level=None)
        db.session.add(st)
        db.session.commit()

        st_id = u.id
        token = create_access_token(identity=str(st_id), additional_claims={"role": "student"})

    headers = {"Authorization": f"Bearer {token}"}

    # 1. Fetch initial profile -> onboarding should be incomplete
    res_init = client.get("/api/student/profile", headers=headers)
    assert res_init.status_code == 200
    assert res_init.json["onboarding_completed"] is False
    assert res_init.json["grade_level"] is None
    assert res_init.json["consent_given"] is False
    assert res_init.json["gaze_calibrated"] is False

    # 2. Update profile with grade, guardian contact, and assent.
    # consent_given in the payload must be ignored (admin-only).
    update_payload = {
        "grade_level": "Grade 6",
        "guardian_name": "Sarah Smith",
        "guardian_email": "sarah.smith@example.com",
        "consent_given": True,
        "student_assent": True,
    }
    res_update = client.patch("/api/student/profile", json=update_payload, headers=headers)
    assert res_update.status_code == 200
    assert res_update.json["onboarding_completed"] is True
    assert res_update.json["grade_level"] == "Grade 6"
    assert res_update.json["guardian_name"] == "Sarah Smith"
    assert res_update.json["guardian_email"] == "sarah.smith@example.com"
    assert res_update.json["consent_given"] is False
    assert res_update.json["student_assent"] is True

    # 3. Verify in DB — guardian contact saved, consent_given remains false
    with app.app_context():
        s = Student.query.filter_by(user_id=st_id).first()
        assert s.grade_level == "Grade 6"
        assert s.guardian_consent is not None
        assert s.guardian_consent.consent_given is False
        assert s.guardian_consent.guardian_name == "Sarah Smith"


def test_student_cannot_set_guardian_consent_via_profile(client, app):
    """Regression: student PATCH must not flip GuardianConsent.consent_given."""
    with app.app_context():
        gl = GradeLevel(name="Grade 7")
        db.session.add(gl)
        db.session.flush()
        u = User(
            email="student_consent_block@test.com",
            password="hashedpassword",
            role="student",
            first_name="Pat",
            last_name="Lee",
        )
        db.session.add(u)
        db.session.flush()
        st = Student(user_id=u.id, grade_level="Grade 7")
        db.session.add(st)
        db.session.flush()
        db.session.add(
            GuardianConsent(
                student_id=st.id,
                guardian_name="Guardian",
                guardian_email="g@example.com",
                consent_given=False,
            )
        )
        db.session.commit()
        token = create_access_token(identity=str(u.id), additional_claims={"role": "student"})
        student_pk = st.id

    headers = {"Authorization": f"Bearer {token}"}
    res = client.patch(
        "/api/student/profile",
        json={"consent_given": True},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json["consent_given"] is False

    with app.app_context():
        consent = GuardianConsent.query.filter_by(student_id=student_pk).first()
        assert consent.consent_given is False


def test_non_student_profile_access_blocked(client, app):
    with app.app_context():
        u = User(
            email="teacher_prof@test.com",
            password="hashedpassword",
            role="teacher",
            first_name="Prof",
            last_name="Oak"
        )
        db.session.add(u)
        db.session.commit()
        token = create_access_token(identity=str(u.id), additional_claims={"role": "teacher"})

    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/student/profile", headers=headers)
    assert res.status_code == 403


def test_gaze_calibration_start_and_persist_helper(client, app):
    """Calibration-only endpoint accepts start; persist helper writes gaze_calibration."""
    with app.app_context():
        u = User(
            email="student_gaze@test.com",
            password="hashedpassword",
            role="student",
            first_name="Gaze",
            last_name="Kid",
        )
        db.session.add(u)
        db.session.flush()
        st = Student(user_id=u.id, grade_level="Grade 6", student_assent=True)
        db.session.add(st)
        db.session.commit()
        token = create_access_token(identity=str(u.id), additional_claims={"role": "student"})
        student_pk = st.id

    headers = {"Authorization": f"Bearer {token}"}
    res = client.post(
        "/api/student/gaze-calibration",
        json={"calibration_phase": "start", "frames": []},
        headers=headers,
    )
    assert res.status_code == 200
    assert "calibration" in res.json
    assert res.json["gaze_calibrated"] is False
    assert res.json["saved"] is False

    with app.app_context():
        from app.routes.student_profile import persist_student_gaze_calibration

        class _FakeScorer:
            def export_calibration(self):
                return {
                    "mapper": {
                        "ok": True,
                        "cx": [0.5, 0.0, 1.0, 0.0],
                        "cy": [0.5, 0.0, 1.0, 0.0],
                        "residual": 0.01,
                        "n_dots": 9,
                        "freeze_head": False,
                        "margin": 0.03,
                    },
                    "yaw0": 0.0,
                    "pitch0": 0.0,
                    "roll0": 0.0,
                    "iris0": [0.5, 0.5],
                    "baseline_locked": True,
                    "head_phase": True,
                }

        from sqlalchemy import inspect as sa_inspect, text
        from app.routes.student_profile import _gaze_calibrated

        cols = {c["name"] for c in sa_inspect(db.engine).get_columns("students")}
        assert "gaze_calibration" in cols, cols
        student = db.session.get(Student, student_pk)
        saved = persist_student_gaze_calibration(
            student, _FakeScorer(), screen={"w": 1920, "h": 1080}
        )
        assert saved is not None
        assert saved["mapper"]["ok"] is True
        assert saved["screen"]["w"] == 1920
        row = db.session.execute(
            text("SELECT gaze_calibration FROM students WHERE id = :id"),
            {"id": student_pk},
        ).fetchone()
        assert row is not None and row[0] is not None, row
        db.session.expire_all()
        st_check = db.session.get(Student, student_pk)
        assert _gaze_calibrated(st_check) is True
        # Profile payload (same process) reflects the saved fit.
        from app.routes.student_profile import _profile_payload

        user = db.session.get(User, st_check.user_id)
        assert _profile_payload(user, st_check)["gaze_calibrated"] is True
