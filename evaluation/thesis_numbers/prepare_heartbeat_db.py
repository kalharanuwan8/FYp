"""Create the throwaway sqlite DB for the heartbeat latency server. Prints module_id."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import bcrypt

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

from app import create_app
from app.extensions import db
from app.db_models import (
    Enrollment,
    GradeLevel,
    GuardianConsent,
    Module,
    Student,
    Subject,
    User,
)

EMAIL = "thesis.heartbeat@luma.demo"
PASSWORD = "ThesisHeartbeat123!"


def main() -> None:
    app = create_app()
    with app.app_context():
        gl = GradeLevel(name="Grade 1")
        db.session.add(gl)
        db.session.flush()
        subject = Subject(
            title="Thesis Heartbeat Course",
            description="throwaway",
            grade_level_id=gl.id,
        )
        db.session.add(subject)
        db.session.flush()
        module = Module(
            title="Thesis Heartbeat Module",
            description="throwaway",
            subject_id=subject.id,
            sequence_order=1,
        )
        db.session.add(module)
        db.session.flush()
        user = User(
            email=EMAIL,
            password=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
            role="student",
            first_name="Thesis",
            last_name="Heartbeat",
            is_active=True,
        )
        db.session.add(user)
        db.session.flush()
        student = Student(user_id=user.id, grade_level="Grade 1")
        db.session.add(student)
        db.session.flush()
        db.session.add(
            GuardianConsent(
                student_id=student.id,
                guardian_name="Thesis Guardian",
                guardian_email="guardian@luma.demo",
                consent_given=True,
            )
        )
        db.session.add(Enrollment(student_id=student.id, subject_id=subject.id))
        db.session.commit()
        print(f"MODULE_ID {int(module.id)}", flush=True)


if __name__ == "__main__":
    main()
