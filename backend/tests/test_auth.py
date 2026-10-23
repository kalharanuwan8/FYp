import bcrypt
import pytest
from flask_jwt_extended import create_access_token
from app.db_models import User, Student, Teacher, GuardianConsent
from app.extensions import db

def test_login_schema_validation(client):
    # Invalid email format
    res = client.post("/api/auth/login", json={"email": "invalid-email", "password": "password123"})
    assert res.status_code == 400
    assert "details" in res.json

def test_login_invalid_password(client, app):
    with app.app_context():
        u = User(
            email="testuser@example.com",
            password=bcrypt.hashpw(b"correctpassword", bcrypt.gensalt()).decode("utf-8"),
            role="student",
            first_name="Test",
            last_name="User"
        )
        db.session.add(u)
        db.session.commit()

    # Wrong password
    res = client.post("/api/auth/login", json={"email": "testuser@example.com", "password": "wrongpassword"})
    assert res.status_code == 401
    assert res.json["error"] == "Invalid email or password"

def test_login_success(client, app):
    with app.app_context():
        u = User(
            email="success@example.com",
            password=bcrypt.hashpw(b"secret123", bcrypt.gensalt()).decode("utf-8"),
            role="teacher",
            first_name="Jane",
            last_name="Doe"
        )
        db.session.add(u)
        db.session.commit()

    res = client.post("/api/auth/login", json={"email": "success@example.com", "password": "secret123"})
    assert res.status_code == 200
    assert "access_token" in res.json
    assert res.json["user"]["role"] == "teacher"
    assert res.json["user"]["first_name"] == "Jane"
    assert res.json["user"]["last_name"] == "Doe"
    assert "password" not in res.json["user"]

def test_register_admin_role_rejected(client, app):
    with app.app_context():
        admin = User(email="admin@test.com", password="hash", role="admin", first_name="Admin", last_name="User")
        db.session.add(admin)
        db.session.commit()
        token = create_access_token(identity=str(admin.id), additional_claims={"role": "admin"})

    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "email": "newadmin@test.com",
        "password": "password123",
        "first_name": "New",
        "last_name": "Admin",
        "role": "admin"
    }
    res = client.post("/api/auth/register", json=payload, headers=headers)
    assert res.status_code == 400
    assert "details" in res.json

def test_register_duplicate_email_rejected(client, app):
    with app.app_context():
        admin = User(email="admin_dup@test.com", password="hash", role="admin", first_name="Admin", last_name="User")
        existing_user = User(email="existing@test.com", password="hash", role="teacher", first_name="Existing", last_name="Teacher")
        db.session.add(admin)
        db.session.add(existing_user)
        db.session.commit()
        token = create_access_token(identity=str(admin.id), additional_claims={"role": "admin"})

    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "email": "existing@test.com",
        "password": "password123",
        "first_name": "Duplicate",
        "last_name": "Teacher",
        "role": "teacher"
    }
    res = client.post("/api/auth/register", json=payload, headers=headers)
    assert res.status_code == 400
    assert res.json["error"] == "A user with this email already exists"

def test_register_student_success(client, app):
    with app.app_context():
        admin = User(email="admin2@test.com", password="hash", role="admin", first_name="Admin", last_name="User")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
        token = create_access_token(identity=str(admin_id), additional_claims={"role": "admin"})

    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "email": "student1@test.com",
        "password": "password123",
        "first_name": "Sammy",
        "last_name": "Student",
        "role": "student",
        "guardian_name": "Parent Person",
        "guardian_email": "parent@test.com"
    }
    res = client.post("/api/auth/register", json=payload, headers=headers)
    assert res.status_code == 201
    assert res.json["message"] == "User registered successfully"

    with app.app_context():
        u = User.query.filter_by(email="student1@test.com").first()
        assert u is not None
        assert u.created_by == admin_id
        student = Student.query.filter_by(user_id=u.id).first()
        assert student is not None
        assert student.pseudonym_id is not None
        consent = GuardianConsent.query.filter_by(student_id=student.id).first()
        assert consent is not None
        assert consent.consent_given is False
        assert consent.guardian_name == "Parent Person"
