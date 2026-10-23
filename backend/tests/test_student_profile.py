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

    # 2. Update profile with Grade Level and Guardian Consent details
    update_payload = {
        "grade_level": "Grade 6",
        "guardian_name": "Sarah Smith",
        "guardian_email": "sarah.smith@example.com",
        "consent_given": True
    }
    res_update = client.patch("/api/student/profile", json=update_payload, headers=headers)
    assert res_update.status_code == 200
    assert res_update.json["onboarding_completed"] is True
    assert res_update.json["grade_level"] == "Grade 6"
    assert res_update.json["guardian_name"] == "Sarah Smith"
    assert res_update.json["guardian_email"] == "sarah.smith@example.com"
    assert res_update.json["consent_given"] is True

    # 3. Verify in DB
    with app.app_context():
        s = Student.query.filter_by(user_id=st_id).first()
        assert s.grade_level == "Grade 6"
        assert s.guardian_consent is not None
        assert s.guardian_consent.consent_given is True
        assert s.guardian_consent.guardian_name == "Sarah Smith"


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
