"""
Idempotent Phase 2A browser-demo fixture.

Creates an isolated demonstration student, enrolled Grade-1 subject, module,
and a playable external sample video. Safe to re-run; does not touch real
learner progress beyond this demo email.

  python seed_phase2a_demo.py

Login: demo.phase2a@luma.com / DemoPhase2A!
"""
from __future__ import annotations

import bcrypt

from app import create_app
from app.extensions import db
from app.db_models import (
    User,
    Student,
    Teacher,
    GuardianConsent,
    GradeLevel,
    Subject,
    TeacherSubject,
    Module,
    ModuleContent,
    Enrollment,
)

DEMO_EMAIL = "demo.phase2a@luma.com"
DEMO_PASSWORD = "DemoPhase2A!"
DEMO_GRADE = "Grade 1"
DEMO_SUBJECT = "Phase 2A Demo Course"
DEMO_MODULE = "Demo Video Lesson"
# Served by Flask /uploads/<filename> (idempotent fixture; not learner data).
DEMO_VIDEO_URL = "/uploads/phase2a_demo.mp4"


def seed_phase2a_demo():
    app = create_app()
    with app.app_context():
        db.create_all()

        grade = GradeLevel.query.filter_by(name=DEMO_GRADE).first()
        if not grade:
            grade = GradeLevel(name=DEMO_GRADE)
            db.session.add(grade)
            db.session.flush()

        teacher_user = User.query.filter_by(email="teacher@luma.com").first()
        if not teacher_user:
            teacher_user = User(
                email="teacher@luma.com",
                password=bcrypt.hashpw(b"Teacher123!", bcrypt.gensalt()).decode("utf-8"),
                role="teacher",
                first_name="Sarah",
                last_name="Jenkins",
            )
            db.session.add(teacher_user)
            db.session.flush()
            db.session.add(Teacher(user_id=teacher_user.id))
            db.session.flush()

        teacher = Teacher.query.filter_by(user_id=teacher_user.id).first()

        subject = Subject.query.filter_by(title=DEMO_SUBJECT, grade_level_id=grade.id).first()
        if not subject:
            subject = Subject(
                title=DEMO_SUBJECT,
                description="Isolated Phase 2A browser verification course.",
                grade_level_id=grade.id,
            )
            db.session.add(subject)
            db.session.flush()

        if teacher and not TeacherSubject.query.filter_by(
            teacher_id=teacher.id, subject_id=subject.id
        ).first():
            db.session.add(TeacherSubject(teacher_id=teacher.id, subject_id=subject.id))

        module = Module.query.filter_by(subject_id=subject.id, title=DEMO_MODULE).first()
        if not module:
            module = Module(
                title=DEMO_MODULE,
                description="Playable demo video for ambient vs pause checks.",
                subject_id=subject.id,
                sequence_order=1,
            )
            db.session.add(module)
            db.session.flush()

        content = ModuleContent.query.filter_by(
            module_id=module.id, title="Demo Sample Video"
        ).first()
        if not content:
            content = ModuleContent(
                module_id=module.id,
                content_type="video",
                title="Demo Sample Video",
                file_url=DEMO_VIDEO_URL,
                summary="Phase 2A demo fixture video.",
            )
            db.session.add(content)
        else:
            content.file_url = DEMO_VIDEO_URL
            content.content_type = "video"

        user = User.query.filter_by(email=DEMO_EMAIL).first()
        if not user:
            user = User(
                email=DEMO_EMAIL,
                password=bcrypt.hashpw(
                    DEMO_PASSWORD.encode("utf-8"), bcrypt.gensalt()
                ).decode("utf-8"),
                role="student",
                first_name="Phase2A",
                last_name="Demo",
            )
            db.session.add(user)
            db.session.flush()
        student = Student.query.filter_by(user_id=user.id).first()
        if not student:
            student = Student(user_id=user.id, grade_level=DEMO_GRADE)
            db.session.add(student)
            db.session.flush()
        else:
            student.grade_level = DEMO_GRADE

        if not GuardianConsent.query.filter_by(student_id=student.id).first():
            db.session.add(
                GuardianConsent(
                    student_id=student.id,
                    guardian_name="Demo Guardian",
                    guardian_email="demo.guardian.phase2a@example.com",
                    consent_given=True,
                )
            )
        else:
            consent = GuardianConsent.query.filter_by(student_id=student.id).first()
            consent.consent_given = True

        if not Enrollment.query.filter_by(
            student_id=student.id, subject_id=subject.id
        ).first():
            db.session.add(
                Enrollment(student_id=student.id, subject_id=subject.id)
            )

        db.session.commit()
        print("Phase 2A demo fixture ready.")
        print(f"  Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print(f"  Grade: {DEMO_GRADE}")
        print(f"  Subject: {DEMO_SUBJECT} (id={subject.id})")
        print(f"  Module: {DEMO_MODULE} (id={module.id})")
        print(f"  Video: {DEMO_VIDEO_URL}")


if __name__ == "__main__":
    seed_phase2a_demo()
