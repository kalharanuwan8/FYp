"""
Idempotent default accounts + grade levels for local / first-boot setup.

Passwords are stored as bcrypt hashes (same format login uses via bcrypt.checkpw).
Called automatically from create_app() when SEED_DEFAULT_ACCOUNTS is true;
backend/seed.py is a thin optional wrapper around the same helpers.
"""

from __future__ import annotations

import logging

import bcrypt

from app.db_models import User, Student, Teacher, GuardianConsent, GradeLevel
from app.extensions import db

logger = logging.getLogger(__name__)

# Single source of truth for demo credentials (also printed by seed.py).
DEFAULT_ACCOUNTS = [
    {
        "email": "admin@luma.com",
        "password": "Admin123!",
        "role": "admin",
        "first_name": "Luma",
        "last_name": "Admin",
    },
    {
        "email": "teacher@luma.com",
        "password": "Teacher123!",
        "role": "teacher",
        "first_name": "Sarah",
        "last_name": "Jenkins",
    },
    {
        "email": "student@luma.com",
        "password": "Student123!",
        "role": "student",
        "first_name": "Alex",
        "last_name": "Smith",
        "guardian_name": "Robert Smith",
        "guardian_email": "robert.smith@example.com",
    },
]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def ensure_grade_levels() -> int:
    """Insert Grade 1–12 if missing. Returns how many rows were added."""
    created = 0
    for i in range(1, 13):
        name = f"Grade {i}"
        if not GradeLevel.query.filter_by(name=name).first():
            db.session.add(GradeLevel(name=name))
            created += 1
    return created


def ensure_default_accounts() -> list[str]:
    """
    Insert missing default users (and role profile / consent rows).
    Existing users are never updated. Returns list of emails that were created.
    """
    created_emails: list[str] = []

    for acct in DEFAULT_ACCOUNTS:
        email = acct["email"]
        if User.query.filter_by(email=email).first():
            continue

        user = User(
            email=email,
            password=hash_password(acct["password"]),
            role=acct["role"],
            first_name=acct["first_name"],
            last_name=acct["last_name"],
        )
        db.session.add(user)
        db.session.flush()

        if acct["role"] == "teacher":
            db.session.add(Teacher(user_id=user.id))
        elif acct["role"] == "student":
            student = Student(user_id=user.id)
            db.session.add(student)
            db.session.flush()
            db.session.add(
                GuardianConsent(
                    student_id=student.id,
                    guardian_name=acct.get("guardian_name", "Guardian"),
                    guardian_email=acct.get("guardian_email", "guardian@example.com"),
                    consent_given=True,
                )
            )

        created_emails.append(email)

    return created_emails


def ensure_default_data() -> dict:
    """
    Ensure grade levels and default accounts exist. Commits once.
    Rolls back and re-raises on failure so callers can decide how to handle it.
    """
    try:
        grades_created = ensure_grade_levels()
        accounts_created = ensure_default_accounts()
        db.session.commit()
        if grades_created or accounts_created:
            logger.info(
                "Default data seed: %s grade level(s), accounts created: %s",
                grades_created,
                accounts_created or "(none)",
            )
        return {
            "grades_created": grades_created,
            "accounts_created": accounts_created,
        }
    except Exception:
        db.session.rollback()
        raise
