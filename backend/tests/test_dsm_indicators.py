"""DSM-5 multi-signal inattention proxies — positive/negative cases + access control."""

from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token

from app.db_models import (
    BehaviourEvent,
    DistractionEvent,
    Enrollment,
    GradeLevel,
    InterventionLog,
    LearningSession,
    Module,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
    QuizQuestionOption,
    Student,
    StudentProgress,
    Subject,
    Teacher,
    TeacherSubject,
    User,
)
from app.extensions import db
from app.services.dsm_indicators import build_dsm_profile


def _seed_pair(app, suffix="dsm"):
    with app.app_context():
        gl = GradeLevel(name=f"Grade DSM {suffix}")
        db.session.add(gl)
        db.session.flush()
        t_u = User(
            email=f"t_{suffix}@test.com",
            password="hash",
            role="teacher",
            first_name="T",
            last_name=suffix,
        )
        s_u = User(
            email=f"s_{suffix}@test.com",
            password="hash",
            role="student",
            first_name="S",
            last_name=suffix,
        )
        outsider = User(
            email=f"out_{suffix}@test.com",
            password="hash",
            role="teacher",
            first_name="Out",
            last_name=suffix,
        )
        db.session.add_all([t_u, s_u, outsider])
        db.session.flush()
        teacher = Teacher(user_id=t_u.id)
        out_t = Teacher(user_id=outsider.id)
        student = Student(user_id=s_u.id, grade_level="Grade 1")
        db.session.add_all([teacher, out_t, student])
        db.session.flush()
        subj = Subject(title=f"DSM Course {suffix}", grade_level_id=gl.id)
        db.session.add(subj)
        db.session.flush()
        db.session.add(TeacherSubject(teacher_id=teacher.id, subject_id=subj.id))
        db.session.add(Enrollment(student_id=student.id, subject_id=subj.id))
        mod = Module(title="M1", subject_id=subj.id, sequence_order=1)
        db.session.add(mod)
        db.session.flush()
        db.session.commit()
        return {
            "teacher_user_id": t_u.id,
            "outsider_user_id": outsider.id,
            "student_user_id": s_u.id,
            "student_id": student.id,
            "teacher_id": teacher.id,
            "module_id": mod.id,
            "subject_id": subj.id,
        }


def test_idle_endpoint_and_dsm1(client, app):
    ids = _seed_pair(app, "idle")
    with app.app_context():
        quiz = Quiz(module_id=ids["module_id"], title="Q", time_limit_minutes=20)
        db.session.add(quiz)
        db.session.flush()
        attempt = QuizAttempt(
            quiz_id=quiz.id,
            student_id=ids["student_id"],
            started_at=datetime.utcnow(),
        )
        db.session.add(attempt)
        db.session.commit()
        attempt_id = attempt.id
        student_id = ids["student_id"]

    token = create_access_token(
        identity=str(ids["student_user_id"]), additional_claims={"role": "student"}
    )
    # Below threshold → rejected
    bad = client.post(
        "/api/behaviour/idle",
        json={"context": "quiz", "duration_seconds": 10, "quiz_attempt_id": attempt_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad.status_code == 400

    ok = client.post(
        "/api/behaviour/idle",
        json={
            "context": "quiz",
            "duration_seconds": 20,
            "quiz_attempt_id": attempt_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 201

    with app.app_context():
        profile = build_dsm_profile(student_id)
        dsm1 = next(i for i in profile["indicators"] if i["id"] == "dsm1_sustain")
        assert dsm1["count"] == 1


def test_dsm2_camera_and_noise(app):
    ids = _seed_pair(app, "ext")
    with app.app_context():
        end = datetime.utcnow()
        start = end - timedelta(minutes=5)
        sess = LearningSession(
            student_id=ids["student_id"],
            module_id=ids["module_id"],
            start_time=start,
            end_time=end,
            is_monitored=True,
        )
        db.session.add(sess)
        db.session.flush()
        db.session.add(
            DistractionEvent(
                session_id=sess.id,
                verdict="distracted",
                confidence=0.9,
                started_at=start + timedelta(seconds=10),
                ended_at=start + timedelta(seconds=20),
            )
        )
        db.session.add(
            InterventionLog(
                session_id=sess.id,
                triggered_at=start + timedelta(seconds=30),
                tier=1,
                intervention_type="environment_noise_notice",
            )
        )
        db.session.commit()
        profile = build_dsm_profile(ids["student_id"])
        dsm2 = next(i for i in profile["indicators"] if i["id"] == "dsm2_external")
        assert dsm2["count"] == 2
        assert dsm2["evidence"]["camera_distracted_episodes"] == 1
        assert dsm2["evidence"]["noise_notices"] == 1


def test_dsm3_overtime_positive_and_negative(app):
    ids = _seed_pair(app, "fin")
    with app.app_context():
        quiz = Quiz(module_id=ids["module_id"], title="Timed", time_limit_minutes=20)
        db.session.add(quiz)
        db.session.flush()
        # Overtime completed
        start = datetime.utcnow() - timedelta(minutes=35)
        att_pos = QuizAttempt(
            quiz_id=quiz.id,
            student_id=ids["student_id"],
            started_at=start,
            completed_at=start + timedelta(minutes=30),
            score=50,
        )
        # Within limit
        start2 = datetime.utcnow() - timedelta(minutes=10)
        att_neg = QuizAttempt(
            quiz_id=quiz.id,
            student_id=ids["student_id"],
            started_at=start2,
            completed_at=start2 + timedelta(minutes=8),
            score=80,
        )
        db.session.add_all([att_pos, att_neg])
        db.session.commit()
        profile = build_dsm_profile(ids["student_id"])
        dsm3 = next(i for i in profile["indicators"] if i["id"] == "dsm3_finish")
        assert dsm3["count"] == 1


def test_dsm4_careless_easy_streak(app):
    ids = _seed_pair(app, "care")
    with app.app_context():
        quiz = Quiz(module_id=ids["module_id"], title="EasyQ")
        db.session.add(quiz)
        db.session.flush()
        qs = []
        for i in range(4):
            q = QuizQuestion(
                quiz_id=quiz.id,
                question_text=f"Q{i}",
                question_type="short_answer",
                correct_answer_text="a",
                sequence_order=i + 1,
                difficulty="easy",
            )
            db.session.add(q)
            qs.append(q)
        db.session.flush()
        att = QuizAttempt(
            quiz_id=quiz.id,
            student_id=ids["student_id"],
            started_at=datetime.utcnow() - timedelta(minutes=5),
            completed_at=datetime.utcnow(),
            score=0,
        )
        db.session.add(att)
        db.session.flush()
        t0 = datetime.utcnow() - timedelta(minutes=4)
        for i, q in enumerate(qs[:3]):
            db.session.add(
                QuizAnswer(
                    attempt_id=att.id,
                    question_id=q.id,
                    answer_text="wrong",
                    is_correct=False,
                    answered_at=t0 + timedelta(seconds=i),
                )
            )
        db.session.commit()
        profile = build_dsm_profile(ids["student_id"])
        dsm4 = next(i for i in profile["indicators"] if i["id"] == "dsm4_careless")
        assert dsm4["count"] == 1

        # Negative: only 2 wrong easy
        att2 = QuizAttempt(
            quiz_id=quiz.id,
            student_id=ids["student_id"],
            started_at=datetime.utcnow() - timedelta(minutes=2),
            completed_at=datetime.utcnow(),
            score=50,
        )
        db.session.add(att2)
        db.session.flush()
        for i, q in enumerate(qs[:2]):
            db.session.add(
                QuizAnswer(
                    attempt_id=att2.id,
                    question_id=q.id,
                    answer_text="wrong",
                    is_correct=False,
                    answered_at=datetime.utcnow() + timedelta(seconds=i),
                )
            )
        db.session.commit()
        profile2 = build_dsm_profile(ids["student_id"])
        dsm4b = next(i for i in profile2["indicators"] if i["id"] == "dsm4_careless")
        # Still 1 from the first attempt only (second has streak 2)
        assert dsm4b["count"] == 1


def test_dsm5_hints_all_questions(app):
    ids = _seed_pair(app, "hint")
    with app.app_context():
        quiz = Quiz(module_id=ids["module_id"], title="Hints")
        db.session.add(quiz)
        db.session.flush()
        qs = []
        for i in range(3):
            q = QuizQuestion(
                quiz_id=quiz.id,
                question_text=f"Q{i}",
                question_type="short_answer",
                correct_answer_text="a",
                sequence_order=i + 1,
                hint_text="think",
            )
            db.session.add(q)
            qs.append(q)
        db.session.flush()
        att = QuizAttempt(
            quiz_id=quiz.id,
            student_id=ids["student_id"],
            started_at=datetime.utcnow() - timedelta(minutes=3),
            completed_at=datetime.utcnow(),
            score=100,
        )
        db.session.add(att)
        db.session.flush()
        for q in qs:
            db.session.add(
                QuizAnswer(
                    attempt_id=att.id,
                    question_id=q.id,
                    answer_text="a",
                    is_correct=True,
                    hint_used=True,
                )
            )
        db.session.commit()
        profile = build_dsm_profile(ids["student_id"])
        dsm5 = next(i for i in profile["indicators"] if i["id"] == "dsm5_hints")
        assert dsm5["count"] == 1


def test_dsm6_fast_and_wrong(app):
    ids = _seed_pair(app, "effort")
    with app.app_context():
        quiz = Quiz(module_id=ids["module_id"], title="Speed")
        db.session.add(quiz)
        db.session.flush()
        qs = []
        for i in range(5):
            q = QuizQuestion(
                quiz_id=quiz.id,
                question_text=f"Q{i}",
                question_type="short_answer",
                correct_answer_text="ok",
                sequence_order=i + 1,
            )
            db.session.add(q)
            qs.append(q)
        db.session.flush()
        att = QuizAttempt(
            quiz_id=quiz.id,
            student_id=ids["student_id"],
            started_at=datetime.utcnow() - timedelta(minutes=2),
            completed_at=datetime.utcnow(),
            score=0,
        )
        db.session.add(att)
        db.session.flush()
        for q in qs:
            db.session.add(
                QuizAnswer(
                    attempt_id=att.id,
                    question_id=q.id,
                    answer_text="nope",
                    is_correct=False,
                    response_ms=800,
                )
            )
        db.session.commit()
        profile = build_dsm_profile(ids["student_id"])
        dsm6 = next(i for i in profile["indicators"] if i["id"] == "dsm6_effort")
        assert dsm6["count"] == 1


def test_dsm7_missed_goal(app):
    ids = _seed_pair(app, "goal")
    with app.app_context():
        db.session.add(
            StudentProgress(
                student_id=ids["student_id"],
                daily_goal_minutes=20,
                today_focus_minutes=0,
                total_focus_minutes=0,
            )
        )
        # Yesterday: only 5 minutes
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        start = datetime.combine(yesterday, datetime.min.time()) + timedelta(hours=10)
        end = start + timedelta(minutes=5)
        db.session.add(
            LearningSession(
                student_id=ids["student_id"],
                module_id=ids["module_id"],
                start_time=start,
                end_time=end,
                is_monitored=True,
            )
        )
        db.session.commit()
        profile = build_dsm_profile(ids["student_id"])
        dsm7 = next(i for i in profile["indicators"] if i["id"] == "dsm7_forgetful")
        assert dsm7["count"] >= 1


def test_teacher_dsm_profile_access(client, app):
    ids = _seed_pair(app, "acl")
    t_token = create_access_token(
        identity=str(ids["teacher_user_id"]), additional_claims={"role": "teacher"}
    )
    out_token = create_access_token(
        identity=str(ids["outsider_user_id"]), additional_claims={"role": "teacher"}
    )
    ok = client.get(
        f"/api/analytics/teacher/students/{ids['student_id']}/dsm-profile",
        headers={"Authorization": f"Bearer {t_token}"},
    )
    assert ok.status_code == 200
    assert len(ok.json["indicators"]) == 7

    forbidden = client.get(
        f"/api/analytics/teacher/students/{ids['student_id']}/dsm-profile",
        headers={"Authorization": f"Bearer {out_token}"},
    )
    assert forbidden.status_code == 403


def test_quiz_create_with_dsm_fields_and_hint(client, app):
    ids = _seed_pair(app, "quizapi")
    t_token = create_access_token(
        identity=str(ids["teacher_user_id"]), additional_claims={"role": "teacher"}
    )
    res = client.post(
        f"/api/courses/modules/{ids['module_id']}/quizzes",
        json={
            "title": "DSM Quiz",
            "time_limit_minutes": 15,
            "questions": [
                {
                    "question_text": "Easy one",
                    "question_type": "multiple_choice",
                    "difficulty": "easy",
                    "hint_text": "Pick the first option",
                    "options": [
                        {"option_text": "A", "is_correct": True},
                        {"option_text": "B", "is_correct": False},
                    ],
                }
            ],
        },
        headers={"Authorization": f"Bearer {t_token}"},
    )
    assert res.status_code == 201, res.json
    assert res.json["time_limit_minutes"] == 15
    assert res.json["questions"][0]["difficulty"] == "easy"
    assert res.json["questions"][0]["has_hint"] is True
    assert res.json["questions"][0]["hint_text"] == "Pick the first option"
