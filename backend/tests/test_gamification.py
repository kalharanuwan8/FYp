import bcrypt
import pytest
from app.extensions import db
from app.db_models import User, Student
from app.services.gamification_service import (
    award_session_xp,
    award_quiz_xp,
    get_progress_payload,
)


def _make_student(email="student@test.com"):
    hashed = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode("utf-8")
    user = User(
        email=email,
        password=hashed,
        first_name="Sam",
        last_name="Student",
        role="student",
    )
    db.session.add(user)
    db.session.flush()
    student = Student(user_id=user.id, grade_level="10")
    db.session.add(student)
    db.session.commit()
    return user, student


def _login(client, email, password="password123"):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    return res.get_json()["access_token"]


def test_award_session_xp_and_first_badge(app):
    with app.app_context():
        _, student = _make_student()
        result = award_session_xp(
            student.id, duration_seconds=600, focus_percentage=80.0
        )
        assert result["focus_minutes"] == 8
        assert result["xp_gained"] == 16
        assert result["progress"]["xp"] == 16
        assert result["progress"]["current_streak"] == 1
        codes = [b["badge"]["code"] for b in result["new_badges"]]
        assert "first_session" in codes


def test_award_quiz_ace(app):
    with app.app_context():
        _, student = _make_student("quiz@test.com")
        result = award_quiz_xp(student.id, correct_count=5, total_questions=5)
        assert result["quiz_ace"] is True
        assert result["xp_gained"] == 5 * 10 + 25
        codes = [b["badge"]["code"] for b in result["new_badges"]]
        assert "quiz_ace" in codes


def test_progress_endpoints(client, app):
    with app.app_context():
        user, student = _make_student("prog@test.com")
        award_session_xp(student.id, duration_seconds=3600, focus_percentage=100.0)

    token = _login(client, "prog@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/student/progress", headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["total_focus_minutes"] >= 60
    assert data["xp"] > 0
    assert any(b["code"] == "focus_60" and b["earned"] for b in data["badge_catalog"])

    res2 = client.get("/api/student/badges", headers=headers)
    assert res2.status_code == 200
    badges = res2.get_json()["badges"]
    assert len(badges) >= 1


def test_ui_preferences_patch(client, app):
    with app.app_context():
        _make_student("prefs@test.com")

    token = _login(client, "prefs@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        "/api/student/profile",
        headers=headers,
        json={
            "grade_level": "10",
            "student_assent": True,
            "ui_preferences": {"theme": "calm-dark", "textSize": "l", "reduceMotion": True},
        },
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ui_preferences"]["theme"] == "calm-dark"
    assert body["student_assent"] is True
    assert body["onboarding_completed"] is True
