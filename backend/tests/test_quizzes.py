import pytest
from flask_jwt_extended import create_access_token
from app.db_models import User, Teacher, Student, GradeLevel, Subject, TeacherSubject, Module, Quiz, QuizQuestion, QuizQuestionOption, ModuleContent, Enrollment
from app.extensions import db

def test_quiz_full_lifecycle_and_grading(client, app):
    with app.app_context():
        gl = GradeLevel(name="Grade 11")
        db.session.add(gl)

        t_user = User(email="t_quiz_grade@test.com", password="hash", role="teacher", first_name="T", last_name="G")
        st_user = User(email="st_quiz_grade@test.com", password="hash", role="student", first_name="S", last_name="G")
        db.session.add(t_user)
        db.session.add(st_user)
        db.session.flush()

        teacher = Teacher(user_id=t_user.id)
        student = Student(user_id=st_user.id)
        db.session.add(teacher)
        db.session.add(student)
        db.session.flush()

        subj = Subject(title="Chemistry 101", grade_level_id=gl.id)
        db.session.add(subj)
        db.session.flush()

        ts = TeacherSubject(teacher_id=teacher.id, subject_id=subj.id)
        enroll = Enrollment(student_id=student.id, subject_id=subj.id)
        db.session.add(ts)
        db.session.add(enroll)
        db.session.flush()

        mod = Module(subject_id=subj.id, title="Module 1: Atoms", sequence_order=1)
        db.session.add(mod)
        db.session.commit()

        mod_id = mod.id
        t_token = create_access_token(identity=str(t_user.id), additional_claims={"role": "teacher"})
        st_token = create_access_token(identity=str(st_user.id), additional_claims={"role": "student"})

    headers_t = {"Authorization": f"Bearer {t_token}"}
    headers_st = {"Authorization": f"Bearer {st_token}"}

    # 1. Teacher creates Quiz
    quiz_payload = {
        "title": "Atomic Structure Quiz",
        "questions": [
            {
                "question_text": "Which particle has a negative charge?",
                "question_type": "multiple_choice",
                "sequence_order": 1,
                "options": [
                    {"option_text": "Proton", "is_correct": False},
                    {"option_text": "Electron", "is_correct": True},
                    {"option_text": "Neutron", "is_correct": False}
                ]
            },
            {
                "question_text": "What is the chemical symbol for Gold?",
                "question_type": "short_answer",
                "sequence_order": 2,
                "correct_answer_text": "Au"
            }
        ]
    }
    res_create = client.post(f"/api/courses/modules/{mod_id}/quizzes", json=quiz_payload, headers=headers_t)
    assert res_create.status_code == 201
    quiz_id = res_create.json["id"]
    q1_id = res_create.json["questions"][0]["id"]
    q1_opt_electron_id = res_create.json["questions"][0]["options"][1]["id"]
    q2_id = res_create.json["questions"][1]["id"]

    # 2. Student starts Attempt
    res_start = client.post(f"/api/courses/quizzes/{quiz_id}/attempts", headers=headers_st)
    assert res_start.status_code == 201
    attempt_id = res_start.json["attempt_id"]

    # 3. Duplicate question_ids submission rejection -> 400
    dup_payload = {
        "answers": [
            {"question_id": q1_id, "selected_option_id": q1_opt_electron_id},
            {"question_id": q1_id, "selected_option_id": q1_opt_electron_id}
        ]
    }
    res_dup = client.post(f"/api/courses/attempts/{attempt_id}/submit", json=dup_payload, headers=headers_st)
    assert res_dup.status_code == 400
    assert "Duplicate question_ids" in str(res_dup.json)

    # 4. Student submits Attempt (100% Score)
    submit_payload = {
        "answers": [
            {"question_id": q1_id, "selected_option_id": q1_opt_electron_id},
            {"question_id": q2_id, "answer_text": "  au  "}  # Case-insensitive & trimmed
        ]
    }
    res_submit = client.post(f"/api/courses/attempts/{attempt_id}/submit", json=submit_payload, headers=headers_st)
    assert res_submit.status_code == 200
    assert res_submit.json["score"] == 100.0
    assert len(res_submit.json["answers"]) == 2
    assert res_submit.json["answers"][0]["is_correct"] is True
    assert res_submit.json["answers"][1]["is_correct"] is True

    # 5. Attempt Idempotency (Duplicate submission blocked -> 400)
    res_sub_dup = client.post(f"/api/courses/attempts/{attempt_id}/submit", json=submit_payload, headers=headers_st)
    assert res_sub_dup.status_code == 400
    assert "already been submitted" in res_sub_dup.json["error"]

    # 6. Single-Attempt Policy Guard (Starting new attempt after completion blocked -> 403)
    res_start_second = client.post(f"/api/courses/quizzes/{quiz_id}/attempts", headers=headers_st)
    assert res_start_second.status_code == 403
    assert "already completed an attempt" in res_start_second.json["error"]

    # 7. GET Quiz Attempts list (Teacher gets attempt with score)
    res_attempts = client.get(f"/api/courses/quizzes/{quiz_id}/attempts", headers=headers_t)
    assert res_attempts.status_code == 200
    assert len(res_attempts.json) == 1
    assert res_attempts.json[0]["score"] == 100.0
