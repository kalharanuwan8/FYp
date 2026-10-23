import pytest
from datetime import datetime, timedelta
from flask_jwt_extended import create_access_token
from app.db_models import (
    User,
    Teacher,
    Student,
    GradeLevel,
    Subject,
    TeacherSubject,
    Module,
    Enrollment,
    LearningSession,
    DistractionEvent,
)
from app.extensions import db


def test_analytics_endpoints(client, app):
    with app.app_context():
        gl = GradeLevel(name="Grade 11")
        db.session.add(gl)
        db.session.flush()

        t_u = User(
            email="t_analytics@test.com",
            password="hash",
            role="teacher",
            first_name="T",
            last_name="A",
        )
        s_u = User(
            email="s_analytics@test.com",
            password="hash",
            role="student",
            first_name="S",
            last_name="A",
        )
        a_u = User(
            email="a_analytics@test.com",
            password="hash",
            role="admin",
            first_name="A",
            last_name="A",
        )
        db.session.add(t_u)
        db.session.add(s_u)
        db.session.add(a_u)
        db.session.flush()

        teacher = Teacher(user_id=t_u.id)
        student = Student(user_id=s_u.id, grade_level="Grade 11")
        db.session.add(teacher)
        db.session.add(student)
        db.session.flush()

        subj = Subject(title="Calculus 101", grade_level_id=gl.id)
        db.session.add(subj)
        db.session.flush()

        ts = TeacherSubject(teacher_id=teacher.id, subject_id=subj.id)
        db.session.add(ts)

        enrollment = Enrollment(student_id=student.id, subject_id=subj.id)
        db.session.add(enrollment)
        db.session.flush()

        mod = Module(title="Limits", subject_id=subj.id, sequence_order=1)
        db.session.add(mod)
        db.session.flush()

        # 100s session with 50s distracted → 50% focus
        end = datetime.utcnow()
        start = end - timedelta(seconds=100)
        sess = LearningSession(
            student_id=student.id,
            module_id=mod.id,
            is_monitored=True,
            start_time=start,
            end_time=end,
        )
        db.session.add(sess)
        db.session.flush()

        ev = DistractionEvent(
            session_id=sess.id,
            verdict="distracted",
            confidence=0.90,
            started_at=start,
            ended_at=start + timedelta(seconds=50),
        )
        db.session.add(ev)
        db.session.commit()

        t_token = create_access_token(
            identity=str(t_u.id), additional_claims={"role": "teacher"}
        )
        s_token = create_access_token(
            identity=str(s_u.id), additional_claims={"role": "student"}
        )
        a_token = create_access_token(
            identity=str(a_u.id), additional_claims={"role": "admin"}
        )

    res_teacher = client.get(
        "/api/analytics/teacher", headers={"Authorization": f"Bearer {t_token}"}
    )
    assert res_teacher.status_code == 200
    assert res_teacher.json["total_students"] == 1
    assert res_teacher.json["total_sessions"] == 1
    assert res_teacher.json["avg_focus_percentage"] == 50.0

    res_student = client.get(
        "/api/analytics/student", headers={"Authorization": f"Bearer {s_token}"}
    )
    assert res_student.status_code == 200
    assert res_student.json["total_sessions"] == 1
    assert res_student.json["avg_focus_percentage"] == 50.0
    assert len(res_student.json["subject_progress"]) == 1

    res_admin = client.get(
        "/api/analytics/admin", headers={"Authorization": f"Bearer {a_token}"}
    )
    assert res_admin.status_code == 200
    assert res_admin.json["total_users"] >= 3
    assert res_admin.json["total_subjects"] >= 1
    assert res_admin.json["platform_avg_focus"] == 50.0
