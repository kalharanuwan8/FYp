import io
import pytest
from flask_jwt_extended import create_access_token
from app.db_models import User, Teacher, Student, GradeLevel, Subject, TeacherSubject, Module, ModuleContent, Enrollment
from app.extensions import db

def test_get_grade_levels(client, app):
    with app.app_context():
        gl1 = GradeLevel(name="Grade 1")
        gl2 = GradeLevel(name="Grade 2")
        db.session.add(gl1)
        db.session.add(gl2)
        db.session.commit()

        u = User(email="user_gl@test.com", password="hash", role="student", first_name="A", last_name="B")
        db.session.add(u)
        db.session.commit()

        token = create_access_token(identity=str(u.id), additional_claims={"role": "student"})

    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/courses/grade-levels", headers=headers)
    assert res.status_code == 200
    assert len(res.json) >= 2
    names = [g["name"] for g in res.json]
    assert "Grade 1" in names
    assert "Grade 2" in names

def test_course_creation_and_ownership(client, app):
    with app.app_context():
        gl = GradeLevel(name="Grade 5")
        db.session.add(gl)

        t_user = User(email="teacher_course@test.com", password="hash", role="teacher", first_name="Teacher", last_name="User")
        db.session.add(t_user)
        db.session.flush()

        teacher = Teacher(user_id=t_user.id)
        db.session.add(teacher)
        db.session.commit()

        gl_id = gl.id
        t_user_id = t_user.id
        token = create_access_token(identity=str(t_user_id), additional_claims={"role": "teacher"})

    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create Subject
    payload = {
        "title": "Mathematics 101",
        "description": "Introductory Algebra",
        "grade_level_id": gl_id
    }
    res = client.post("/api/courses/subjects", json=payload, headers=headers)
    assert res.status_code == 201
    subject_id = res.json["id"]
    assert res.json["title"] == "Mathematics 101"

    # Verify TeacherSubject row was created atomically
    with app.app_context():
        ts = TeacherSubject.query.filter_by(subject_id=subject_id).first()
        assert ts is not None

    # 2. Add Module
    module_payload = {
        "title": "Module 1: Foundations",
        "description": "Basic Numbers",
        "sequence_order": 1
    }
    res_mod = client.post(f"/api/courses/subjects/{subject_id}/modules", json=module_payload, headers=headers)
    assert res_mod.status_code == 201
    assert res_mod.json["title"] == "Module 1: Foundations"

    # 3. Get Subject Detail (includes nested modules)
    res_detail = client.get(f"/api/courses/subjects/{subject_id}", headers=headers)
    assert res_detail.status_code == 200
    assert len(res_detail.json["modules"]) == 1
    assert res_detail.json["modules"][0]["sequence_order"] == 1

def test_archive_subject(client, app):
    with app.app_context():
        gl = GradeLevel(name="Grade 7")
        db.session.add(gl)
        
        t_user = User(email="t_archive@test.com", password="hash", role="teacher", first_name="T", last_name="A")
        db.session.add(t_user)
        db.session.flush()
        teacher = Teacher(user_id=t_user.id)
        db.session.add(teacher)
        db.session.flush()

        subj = Subject(title="History 101", grade_level_id=gl.id, is_archived=False)
        db.session.add(subj)
        db.session.flush()

        ts = TeacherSubject(teacher_id=teacher.id, subject_id=subj.id)
        db.session.add(ts)
        db.session.commit()

        subj_id = subj.id
        token = create_access_token(identity=str(t_user.id), additional_claims={"role": "teacher"})

    headers = {"Authorization": f"Bearer {token}"}

    # Archive subject
    res = client.patch(f"/api/courses/subjects/{subj_id}/archive", json={"is_archived": True}, headers=headers)
    assert res.status_code == 200
    assert res.json["is_archived"] is True

    with app.app_context():
        s = db.session.get(Subject, subj_id)
        assert s.is_archived is True
        
        admin_u = User(email="admin_arc@test.com", password="hash", role="admin", first_name="A", last_name="M")
        student_u = User(email="stud_arc@test.com", password="hash", role="student", first_name="S", last_name="T")
        db.session.add(admin_u)
        db.session.add(student_u)
        db.session.commit()
        admin_token = create_access_token(identity=str(admin_u.id), additional_claims={"role": "admin"})
        student_token = create_access_token(identity=str(student_u.id), additional_claims={"role": "student"})

    # Admin CAN view archived subject detail
    res_admin = client.get(f"/api/courses/subjects/{subj_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200

    # Student CANNOT view archived subject detail (404)
    res_student = client.get(f"/api/courses/subjects/{subj_id}", headers={"Authorization": f"Bearer {student_token}"})
    assert res_student.status_code == 404

def test_role_based_subject_list_branching(client, app):
    with app.app_context():
        gl_g8 = GradeLevel(name="Grade 8")
        gl_g9 = GradeLevel(name="Grade 9")
        db.session.add(gl_g8)
        db.session.add(gl_g9)
        db.session.flush()
        
        # Teacher 1
        t1_u = User(email="t1_branch@test.com", password="hash", role="teacher", first_name="T1", last_name="B")
        db.session.add(t1_u)
        db.session.flush()
        t1 = Teacher(user_id=t1_u.id)
        db.session.add(t1)
        db.session.flush()

        s1 = Subject(title="T1 Subject", grade_level_id=gl_g8.id)
        s2 = Subject(title="Grade 9 Subject", grade_level_id=gl_g9.id)
        db.session.add(s1)
        db.session.add(s2)
        db.session.flush()

        ts1 = TeacherSubject(teacher_id=t1.id, subject_id=s1.id)
        db.session.add(ts1)

        # Student User in Grade 8
        st_u = User(email="student_branch@test.com", password="hash", role="student", first_name="St", last_name="B")
        db.session.add(st_u)
        db.session.flush()
        student = Student(user_id=st_u.id, grade_level="Grade 8")
        db.session.add(student)
        db.session.commit()

        t1_token = create_access_token(identity=str(t1_u.id), additional_claims={"role": "teacher"})
        st_token = create_access_token(identity=str(st_u.id), additional_claims={"role": "student"})

    # Teacher 1 gets assigned subjects (1 subject)
    res_t1 = client.get("/api/courses/subjects", headers={"Authorization": f"Bearer {t1_token}"})
    assert res_t1.status_code == 200
    assert len(res_t1.json["subjects"]) == 1
    assert res_t1.json["subjects"][0]["title"] == "T1 Subject"

    # Grade 8 Student gets Grade 8 subjects only (1 subject, excluding Grade 9)
    res_st = client.get("/api/courses/subjects", headers={"Authorization": f"Bearer {st_token}"})
    assert res_st.status_code == 200
    assert len(res_st.json["subjects"]) == 1
    assert res_st.json["subjects"][0]["title"] == "T1 Subject"

def test_student_enrollment_lifecycle(client, app):
    with app.app_context():
        gl_g3 = GradeLevel(name="Grade 3")
        gl_g4 = GradeLevel(name="Grade 4")
        db.session.add(gl_g3)
        db.session.add(gl_g4)
        db.session.flush()

        s_g3 = Subject(title="Science Grade 3", grade_level_id=gl_g3.id)
        s_g4 = Subject(title="Science Grade 4", grade_level_id=gl_g4.id)
        db.session.add(s_g3)
        db.session.add(s_g4)
        db.session.flush()

        st_u = User(email="st_enroll@test.com", password="hash", role="student", first_name="S", last_name="E")
        db.session.add(st_u)
        db.session.flush()
        student = Student(user_id=st_u.id, grade_level="Grade 3")
        db.session.add(student)
        db.session.commit()

        s_g3_id = s_g3.id
        s_g4_id = s_g4.id
        st_token = create_access_token(identity=str(st_u.id), additional_claims={"role": "student"})

    headers = {"Authorization": f"Bearer {st_token}"}

    # 1. Enroll in mismatched Grade 4 subject -> 403 Forbidden
    res_err_grade = client.post(f"/api/courses/subjects/{s_g4_id}/enroll", headers=headers)
    assert res_err_grade.status_code == 403
    assert "not available for your grade level" in res_err_grade.json["error"]

    # 2. Enroll in matching Grade 3 subject -> 201 Created
    res_enroll = client.post(f"/api/courses/subjects/{s_g3_id}/enroll", headers=headers)
    assert res_enroll.status_code == 201
    assert res_enroll.json["subject_id"] == s_g3_id

    # 3. Duplicate enrollment -> 409 Conflict
    res_dup = client.post(f"/api/courses/subjects/{s_g3_id}/enroll", headers=headers)
    assert res_dup.status_code == 409

    # 4. List my enrollments -> 200 (contains 1 enrolled subject)
    res_list = client.get("/api/courses/my-enrollments", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json["enrollments"]) == 1
    assert res_list.json["enrollments"][0]["title"] == "Science Grade 3"

    # 5. Drop enrollment -> 200
    res_drop = client.delete(f"/api/courses/subjects/{s_g3_id}/enroll", headers=headers)
    assert res_drop.status_code == 200

    # 6. Verify list empty after drop
    res_list_after = client.get("/api/courses/my-enrollments", headers=headers)
    assert res_list_after.status_code == 200
    assert len(res_list_after.json["enrollments"]) == 0

def test_material_file_upload(client, app):
    with app.app_context():
        t_u = User(email="t_upload@test.com", password="hash", role="teacher", first_name="T", last_name="U")
        db.session.add(t_u)
        db.session.flush()
        teacher = Teacher(user_id=t_u.id)
        db.session.add(teacher)
        db.session.commit()

        token = create_access_token(identity=str(t_u.id), additional_claims={"role": "teacher"})

    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "file": (io.BytesIO(b"Sample PDF content"), "chapter1_guide.pdf")
    }

    res = client.post(
        "/api/courses/upload",
        data=data,
        content_type="multipart/form-data",
        headers=headers
    )

    assert res.status_code == 201
    assert "file_url" in res.json
    assert res.json["file_url"].startswith("/uploads/")
