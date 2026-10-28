"""Security fixes: authenticated material files, quiz ownership, no student milestone answers."""
import os

from flask_jwt_extended import create_access_token

from app.db_models import (
    User,
    Teacher,
    Student,
    GradeLevel,
    Subject,
    TeacherSubject,
    Module,
    ModuleContent,
    ModuleMilestoneItem,
    Enrollment,
    Quiz,
)
from app.extensions import db


def _seed_course(app):
    with app.app_context():
        gl = GradeLevel(name="G-sec")
        db.session.add(gl)
        db.session.flush()

        t_user = User(
            email="t_sec@test.com",
            password="hash",
            role="teacher",
            first_name="T",
            last_name="S",
        )
        other_t = User(
            email="t_other_sec@test.com",
            password="hash",
            role="teacher",
            first_name="O",
            last_name="T",
        )
        st_user = User(
            email="st_sec@test.com",
            password="hash",
            role="student",
            first_name="S",
            last_name="S",
        )
        outsider = User(
            email="st_out_sec@test.com",
            password="hash",
            role="student",
            first_name="X",
            last_name="Y",
        )
        db.session.add_all([t_user, other_t, st_user, outsider])
        db.session.flush()

        teacher = Teacher(user_id=t_user.id)
        other_teacher = Teacher(user_id=other_t.id)
        student = Student(user_id=st_user.id)
        out_student = Student(user_id=outsider.id)
        db.session.add_all([teacher, other_teacher, student, out_student])
        db.session.flush()

        subj = Subject(title="Sec Course", grade_level_id=gl.id)
        db.session.add(subj)
        db.session.flush()
        db.session.add(TeacherSubject(teacher_id=teacher.id, subject_id=subj.id))
        db.session.add(Enrollment(student_id=student.id, subject_id=subj.id))
        db.session.flush()

        mod = Module(subject_id=subj.id, title="M1", sequence_order=1)
        db.session.add(mod)
        db.session.flush()

        upload_folder = app.config.get("UPLOAD_FOLDER", "uploads")
        if not os.path.isabs(upload_folder):
            upload_folder = os.path.join(app.root_path, "..", upload_folder)
        os.makedirs(upload_folder, exist_ok=True)
        fname = "sec_test_material.txt"
        fpath = os.path.join(upload_folder, fname)
        with open(fpath, "w", encoding="utf-8") as fh:
            fh.write("secret notes")

        content = ModuleContent(
            module_id=mod.id,
            content_type="document",
            title="Notes",
            file_url=f"/uploads/{fname}",
            summary="Approved summary",
        )
        db.session.add(content)
        db.session.flush()
        db.session.add(
            ModuleMilestoneItem(
                module_content_id=content.id,
                question="What is 2+2?",
                options_json=["3", "4", "5"],
                correct_option=1,
                hint_text="count",
                sequence_order=1,
                is_active=True,
            )
        )
        quiz = Quiz(module_id=mod.id, title="Q1")
        db.session.add(quiz)
        db.session.commit()

        return {
            "subject_id": subj.id,
            "module_id": mod.id,
            "material_id": content.id,
            "quiz_id": quiz.id,
            "filename": fname,
            "t_token": create_access_token(
                identity=str(t_user.id), additional_claims={"role": "teacher"}
            ),
            "other_t_token": create_access_token(
                identity=str(other_t.id), additional_claims={"role": "teacher"}
            ),
            "st_token": create_access_token(
                identity=str(st_user.id), additional_claims={"role": "student"}
            ),
            "out_token": create_access_token(
                identity=str(outsider.id), additional_claims={"role": "student"}
            ),
        }


def test_public_uploads_blocked(client, app):
    ids = _seed_course(app)
    res = client.get(f"/uploads/{ids['filename']}")
    assert res.status_code == 401


def test_material_file_requires_enrolment_or_ownership(client, app):
    ids = _seed_course(app)
    mid = ids["material_id"]

    # No auth
    assert client.get(f"/api/courses/materials/{mid}/file").status_code == 401

    # Enrolled student OK
    res = client.get(
        f"/api/courses/materials/{mid}/file",
        headers={"Authorization": f"Bearer {ids['st_token']}"},
    )
    assert res.status_code == 200
    assert b"secret notes" in res.data

    # Query-string token also OK (video src path)
    res_q = client.get(f"/api/courses/materials/{mid}/file?token={ids['st_token']}")
    assert res_q.status_code == 200

    # Non-enrolled student forbidden
    res_out = client.get(
        f"/api/courses/materials/{mid}/file",
        headers={"Authorization": f"Bearer {ids['out_token']}"},
    )
    assert res_out.status_code == 403

    # Owning teacher OK
    res_t = client.get(
        f"/api/courses/materials/{mid}/file",
        headers={"Authorization": f"Bearer {ids['t_token']}"},
    )
    assert res_t.status_code == 200

    # Other teacher forbidden
    res_ot = client.get(
        f"/api/courses/materials/{mid}/file",
        headers={"Authorization": f"Bearer {ids['other_t_token']}"},
    )
    assert res_ot.status_code == 403


def test_student_subject_detail_hides_milestone_answers(client, app):
    ids = _seed_course(app)
    res = client.get(
        f"/api/courses/subjects/{ids['subject_id']}",
        headers={"Authorization": f"Bearer {ids['st_token']}"},
    )
    assert res.status_code == 200
    milestones = res.json["modules"][0]["contents"][0]["milestones"]
    assert len(milestones) == 1
    assert "correct_option" not in milestones[0]
    assert milestones[0]["question"] == "What is 2+2?"

    res_t = client.get(
        f"/api/courses/subjects/{ids['subject_id']}",
        headers={"Authorization": f"Bearer {ids['t_token']}"},
    )
    assert res_t.status_code == 200
    t_ms = res_t.json["modules"][0]["contents"][0]["milestones"]
    assert t_ms[0]["correct_option"] == 1


def test_quiz_read_requires_ownership_or_enrolment(client, app):
    ids = _seed_course(app)
    quiz_id = ids["quiz_id"]
    module_id = ids["module_id"]

    # Other teacher cannot list or read
    assert (
        client.get(
            f"/api/courses/modules/{module_id}/quizzes",
            headers={"Authorization": f"Bearer {ids['other_t_token']}"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/courses/quizzes/{quiz_id}",
            headers={"Authorization": f"Bearer {ids['other_t_token']}"},
        ).status_code
        == 403
    )

    # Non-enrolled student cannot read
    assert (
        client.get(
            f"/api/courses/quizzes/{quiz_id}",
            headers={"Authorization": f"Bearer {ids['out_token']}"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/courses/quizzes/{quiz_id}/attempts",
            headers={"Authorization": f"Bearer {ids['out_token']}"},
        ).status_code
        == 403
    )

    # Enrolled student can read (no answers revealed)
    res = client.get(
        f"/api/courses/quizzes/{quiz_id}",
        headers={"Authorization": f"Bearer {ids['st_token']}"},
    )
    assert res.status_code == 200
