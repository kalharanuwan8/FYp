"""Tests for idempotent default account seeding (bcrypt + profiles)."""

import bcrypt
import pytest

from app.db_models import User, Student, Teacher, GuardianConsent, GradeLevel
from app.extensions import db
from app.services.default_accounts import DEFAULT_ACCOUNTS, ensure_default_data


def test_ensure_default_data_creates_accounts_and_is_idempotent(app):
    with app.app_context():
        assert User.query.count() == 0

        first = ensure_default_data()
        assert first["grades_created"] == 12
        assert set(first["accounts_created"]) == {a["email"] for a in DEFAULT_ACCOUNTS}
        assert User.query.count() == 3
        assert GradeLevel.query.count() == 12

        second = ensure_default_data()
        assert second["grades_created"] == 0
        assert second["accounts_created"] == []
        assert User.query.count() == 3

        for acct in DEFAULT_ACCOUNTS:
            user = User.query.filter_by(email=acct["email"]).first()
            assert user is not None
            assert user.role == acct["role"]
            assert user.first_name == acct["first_name"]
            assert user.last_name == acct["last_name"]
            assert bcrypt.checkpw(
                acct["password"].encode("utf-8"),
                user.password.encode("utf-8"),
            )
            assert user.password.startswith("$2")

        teacher_user = User.query.filter_by(email="teacher@luma.com").first()
        assert Teacher.query.filter_by(user_id=teacher_user.id).first() is not None

        student_user = User.query.filter_by(email="student@luma.com").first()
        student = Student.query.filter_by(user_id=student_user.id).first()
        assert student is not None
        consent = GuardianConsent.query.filter_by(student_id=student.id).first()
        assert consent is not None
        assert consent.consent_given is True
        assert consent.guardian_name == "Robert Smith"


def test_default_student_can_login(client, app):
    with app.app_context():
        ensure_default_data()

    resp = client.post(
        "/api/auth/login",
        json={"email": "student@luma.com", "password": "Student123!"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "access_token" in body
    assert body["user"]["email"] == "student@luma.com"
    assert body["user"]["role"] == "student"


def test_create_app_testing_does_not_auto_seed(app):
    """TestingConfig sets SEED_DEFAULT_ACCOUNTS=False so fixtures stay empty."""
    assert app.config["SEED_DEFAULT_ACCOUNTS"] is False
    with app.app_context():
        assert User.query.count() == 0
