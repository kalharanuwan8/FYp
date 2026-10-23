import io
import pytest
from flask_jwt_extended import create_access_token
from app.db_models import User, Student, GuardianConsent, GradeLevel, SystemSetting
from app.extensions import db

def test_admin_list_users(client, app, admin_user):
    with app.app_context():
        u1 = User(email="student1@test.com", password="hash", role="student", first_name="Alex", last_name="Smith")
        db.session.add(u1)
        db.session.flush()
        s1 = Student(user_id=u1.id)
        db.session.add(s1)
        db.session.flush()
        c1 = GuardianConsent(student_id=s1.id, guardian_name="Parent", guardian_email="p@test.com", consent_given=True)
        db.session.add(c1)

        u2 = User(email="teacher1@test.com", password="hash", role="teacher", first_name="Sarah", last_name="Jenkins")
        db.session.add(u2)
        db.session.commit()

        token = create_access_token(identity=str(admin_user.id), additional_claims={"role": "admin"})

    headers = {"Authorization": f"Bearer {token}"}

    # 1. Test List all
    res = client.get("/api/admin/users", headers=headers)
    assert res.status_code == 200
    assert "users" in res.json
    assert res.json["total"] >= 3

    # 2. Test Role Filter
    res_student = client.get("/api/admin/users?role=student", headers=headers)
    assert res_student.status_code == 200
    assert len(res_student.json["users"]) == 1
    assert res_student.json["users"][0]["email"] == "student1@test.com"
    assert res_student.json["users"][0]["guardian_consent_given"] is True

    # 3. Test Search Filter
    res_search = client.get("/api/admin/users?search=Sarah", headers=headers)
    assert res_search.status_code == 200
    assert len(res_search.json["users"]) == 1
    assert res_search.json["users"][0]["email"] == "teacher1@test.com"

def test_admin_deactivate_user(client, app, admin_user):
    with app.app_context():
        target = User(email="target@test.com", password="hash", role="student", first_name="Target", last_name="User")
        db.session.add(target)
        db.session.commit()
        target_id = target.id
        token = create_access_token(identity=str(admin_user.id), additional_claims={"role": "admin"})

    headers = {"Authorization": f"Bearer {token}"}
    
    # Deactivate target user
    res = client.patch(f"/api/admin/users/{target_id}/status", json={"is_active": False}, headers=headers)
    assert res.status_code == 200
    assert res.json["is_active"] is False

    with app.app_context():
        u = db.session.get(User, target_id)
        assert u.is_active is False

def test_admin_self_deactivation_blocked(client, app, admin_user):
    with app.app_context():
        token = create_access_token(identity=str(admin_user.id), additional_claims={"role": "admin"})

    headers = {"Authorization": f"Bearer {token}"}
    res = client.patch(f"/api/admin/users/{admin_user.id}/status", json={"is_active": False}, headers=headers)
    assert res.status_code == 400
    assert "Admin accounts cannot deactivate their own account" in res.json["error"]

def test_admin_bulk_import_users(client, app, admin_user):
    with app.app_context():
        gl = GradeLevel(name="Grade 5")
        db.session.add(gl)
        db.session.commit()
        token = create_access_token(identity=str(admin_user.id), additional_claims={"role": "admin"})

    headers = {"Authorization": f"Bearer {token}"}

    csv_data = (
        "email,password,first_name,last_name,role,grade_level,guardian_name,guardian_email\n"
        "bulk_student1@test.com,Pass123!,Student,One,student,Grade 5,Parent One,p1@test.com\n"
        "bulk_teacher1@test.com,Pass123!,Teacher,One,teacher,,,\n"
        "invalid_role@test.com,Pass123!,Bad,Role,principal,,,\n"
    )

    data = {
        "file": (io.BytesIO(csv_data.encode("utf-8")), "users.csv")
    }

    res = client.post(
        "/api/admin/users/bulk-import",
        data=data,
        content_type="multipart/form-data",
        headers=headers
    )

    assert res.status_code == 200
    assert res.json["created"] == 2
    assert res.json["failed"] == 1
    assert len(res.json["errors"]) == 1
    assert res.json["errors"][0]["row_number"] == 4

def test_admin_settings_lifecycle(client, app, admin_user):
    with app.app_context():
        token = create_access_token(identity=str(admin_user.id), additional_claims={"role": "admin"})

    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET settings
    res = client.get("/api/admin/settings", headers=headers)
    assert res.status_code == 200
    assert "intervention_min_cooldown_seconds" in res.json
    assert "intervention_max_cooldown_seconds" in res.json
    assert "data_retention_days" in res.json

    # 2. PATCH unknown key rejected
    res_unk = client.patch("/api/admin/settings", json={
        "settings": {"unsupported_key": "999"}
    }, headers=headers)
    assert res_unk.status_code == 400
    assert "Unknown setting key" in str(res_unk.json["details"])

    # 3. PATCH invalid settings (min > max)
    res_bad = client.patch("/api/admin/settings", json={
        "settings": {
            "intervention_min_cooldown_seconds": 300,
            "intervention_max_cooldown_seconds": 60
        }
    }, headers=headers)
    assert res_bad.status_code == 400
    assert "details" in res_bad.json

    # 4. PATCH valid settings
    res_good = client.patch("/api/admin/settings", json={
        "settings": {
            "intervention_min_cooldown_seconds": 45,
            "intervention_max_cooldown_seconds": 180,
            "data_retention_days": 120
        }
    }, headers=headers)
    assert res_good.status_code == 200
    assert res_good.json["intervention_min_cooldown_seconds"] == "45"
    assert res_good.json["intervention_max_cooldown_seconds"] == "180"
    assert res_good.json["data_retention_days"] == "120"

def test_non_admin_settings_access_blocked(client, app):
    with app.app_context():
        student_u = User(email="stud_sett@test.com", password="hash", role="student", first_name="S", last_name="S")
        teacher_u = User(email="teach_sett@test.com", password="hash", role="teacher", first_name="T", last_name="T")
        db.session.add(student_u)
        db.session.add(teacher_u)
        db.session.commit()

        st_token = create_access_token(identity=str(student_u.id), additional_claims={"role": "student"})
        tc_token = create_access_token(identity=str(teacher_u.id), additional_claims={"role": "teacher"})

    # Student attempting to access admin settings -> 403
    res_st = client.get("/api/admin/settings", headers={"Authorization": f"Bearer {st_token}"})
    assert res_st.status_code == 403

    # Teacher attempting to access admin settings -> 403
    res_tc = client.get("/api/admin/settings", headers={"Authorization": f"Bearer {tc_token}"})
    assert res_tc.status_code == 403
