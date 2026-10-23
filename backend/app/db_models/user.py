"""
Matches the users / students / teachers / guardian_consents tables
exactly as specified in the finalized DB schema.
"""

import uuid
from datetime import datetime
from app.extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=False)
    password = db.Column(db.String, nullable=False)  # bcrypt hash, never plaintext
    role = db.Column(db.Enum("admin", "teacher", "student", name="user_role"), nullable=False)
    first_name = db.Column(db.String, nullable=False)
    last_name = db.Column(db.String, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    # Self-referencing FK: which Admin created this account (FR-AUTH-03)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    creator = db.relationship("User", remote_side=[id], backref="created_users")
    student_profile = db.relationship("Student", back_populates="user", uselist=False)
    teacher_profile = db.relationship("Teacher", back_populates="user", uselist=False)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "is_active": self.is_active,
        }


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    # FR-MON... / NFR-PRIV-02: pseudonymous ID used for anything joinable to
    # monitoring/analytics data, so raw identity never needs to travel with it.
    pseudonym_id = db.Column(
        db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4())
    )

    date_of_birth = db.Column(db.Date, nullable=True)
    grade_level = db.Column(db.String, nullable=True)
    # ADHD-friendly UI prefs: theme, textSize, reduceMotion, sounds, etc.
    ui_preferences = db.Column(db.JSON, nullable=True)
    # Soft assent that the student understands focus buddy (guardian consent stays separate)
    student_assent = db.Column(db.Boolean, default=False)
    onboarding_completed = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship("User", back_populates="student_profile")
    guardian_consent = db.relationship(
        "GuardianConsent", back_populates="student", uselist=False
    )
    enrollments = db.relationship("Enrollment", back_populates="student")
    sessions = db.relationship("LearningSession", back_populates="student")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "pseudonym_id": self.pseudonym_id,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else None,
            "grade_level": self.grade_level,
            "guardian_consent_given": (
                self.guardian_consent.consent_given if self.guardian_consent else False
            ),
        }


class GuardianConsent(db.Model):
    __tablename__ = "guardian_consents"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), unique=True, nullable=False)
    guardian_name = db.Column(db.String, nullable=False)
    guardian_email = db.Column(db.String, nullable=False)
    consent_given = db.Column(db.Boolean, default=False)
    consented_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("Student", back_populates="guardian_consent")


class Teacher(db.Model):
    __tablename__ = "teachers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship("User", back_populates="teacher_profile")
    subjects = db.relationship("TeacherSubject", back_populates="teacher")