"""
TEMPORARY screenshot fixture — safe to delete after thesis screenshots.

- Renames student@luma.com → Kalhara
- Renames teacher@luma.com → Mrs. Nayanaransi
- Creates subject "UI/UX Engineering" (+ extras) assigned to the teacher
- Enrols the student (dummy XP / streak / focus sessions and filler subjects are
  commented out for the doctor demo; see the DEMO comments below)

  python seed_ui_screenshots.py

Logins:
  student@luma.com / Student123!
  teacher@luma.com / Teacher123!
"""
from __future__ import annotations

from datetime import datetime, timedelta, date

from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.db_models import (
    User,
    Student,
    Teacher,
    GradeLevel,
    Subject,
    TeacherSubject,
    Module,
    ModuleContent,
    Enrollment,
    LearningSession,
    StudentProgress,
)

STUDENT_EMAIL = "student@luma.com"
TEACHER_EMAIL = "teacher@luma.com"
SUBJECT_TITLE = "UI/UX Engineering"
GRADE_NAME = "Grade 12"

EXTRA_SUBJECTS = [
    {
        "title": "Interaction Design Studio",
        "description": "Wireframes, flows, and usability heuristics for product interfaces.",
    },
    {
        "title": "Visual Systems & Typography",
        "description": "Type scales, colour tokens, and consistent component libraries.",
    },
]


def _ensure_teacher():
    teacher_user = User.query.filter_by(email=TEACHER_EMAIL).first()
    if not teacher_user:
        raise SystemExit(f"{TEACHER_EMAIL} missing — start the backend once so defaults seed.")
    # Dashboard greets with first_name only — keep full display name there
    teacher_user.first_name = "Mrs. Nayanaransi"
    teacher_user.last_name = ""
    print(f"  · Teacher display name → Mrs. Nayanaransi ({TEACHER_EMAIL})")
    teacher = Teacher.query.filter_by(user_id=teacher_user.id).first()
    if not teacher:
        teacher = Teacher(user_id=teacher_user.id)
        db.session.add(teacher)
        db.session.flush()
    return teacher


def _ensure_subject(title, description, grade_id, teacher):
    subject = Subject.query.filter_by(title=title, grade_level_id=grade_id).first()
    if not subject:
        subject = Subject(title=title, description=description, grade_level_id=grade_id)
        db.session.add(subject)
        db.session.flush()
        print(f"  + Subject: {title}")
    else:
        subject.description = description
        print(f"  · Subject already present: {title}")

    if not TeacherSubject.query.filter_by(
        teacher_id=teacher.id, subject_id=subject.id
    ).first():
        db.session.add(TeacherSubject(teacher_id=teacher.id, subject_id=subject.id))
    return subject


def _ensure_modules(subject):
    specs = [
        (
            1,
            "Foundations of UX",
            "Users, jobs-to-be-done, and research basics.",
            [
                ("Introduction to UX Thinking", "document"),
                ("Empathy Map Walkthrough", "video"),
            ],
        ),
        (
            2,
            "Interface Patterns",
            "Navigation, forms, feedback, and accessibility.",
            [
                ("Component Anatomy", "document"),
                ("Accessible Forms Demo", "video"),
            ],
        ),
        (
            3,
            "Prototype & Critique",
            "Low-fi to high-fi flows and design critique.",
            [
                ("Critique Checklist", "document"),
            ],
        ),
    ]
    modules = []
    for order, title, desc, contents in specs:
        mod = Module.query.filter_by(subject_id=subject.id, title=title).first()
        if not mod:
            mod = Module(
                title=title,
                description=desc,
                subject_id=subject.id,
                sequence_order=order,
            )
            db.session.add(mod)
            db.session.flush()
            print(f"  + Module: {title}")
        modules.append(mod)
        for c_title, c_type in contents:
            exists = ModuleContent.query.filter_by(
                module_id=mod.id, title=c_title
            ).first()
            if exists:
                continue
            # Postgres column is content_type_enum; ORM String needs an explicit cast.
            dialect = db.engine.dialect.name
            if dialect == "postgresql":
                db.session.execute(
                    text(
                        """
                        INSERT INTO module_contents
                            (module_id, content_type, title, file_url, summary, created_at, updated_at)
                        VALUES
                            (:mid, CAST(:ctype AS content_type_enum), :title, NULL, :summary, NOW(), NOW())
                        """
                    ),
                    {
                        "mid": mod.id,
                        "ctype": c_type,
                        "title": c_title,
                        "summary": f"Screenshot fixture — {c_title}",
                    },
                )
            else:
                db.session.add(
                    ModuleContent(
                        module_id=mod.id,
                        content_type=c_type,
                        title=c_title,
                        file_url=None,
                        summary=f"Screenshot fixture — {c_title}",
                    )
                )
        db.session.flush()
    return modules


def _ensure_enrollment(student, subject, enrolled_at=None):
    row = Enrollment.query.filter_by(
        student_id=student.id, subject_id=subject.id
    ).first()
    if not row:
        row = Enrollment(student_id=student.id, subject_id=subject.id)
        db.session.add(row)
        db.session.flush()
        print(f"  + Enrolled in {subject.title}")
    if enrolled_at is not None:
        row.enrolled_at = enrolled_at


def _prune_other_enrollments(student, keep_subject_ids):
    """Keep screenshot subjects only so the continue card shows UI/UX first."""
    keep = set(keep_subject_ids)
    removed = 0
    for e in Enrollment.query.filter_by(student_id=student.id).all():
        if e.subject_id not in keep:
            db.session.delete(e)
            removed += 1
    if removed:
        print(f"  · Removed {removed} other enrollment(s) for a clean dashboard")


def _ensure_progress(student):
    prog = StudentProgress.query.filter_by(student_id=student.id).first()
    if not prog:
        prog = StudentProgress(student_id=student.id)
        db.session.add(prog)
        db.session.flush()
    prog.xp = 245
    prog.level = 3
    prog.current_streak = 4
    prog.longest_streak = 7
    prog.last_active_date = date.today()
    prog.daily_goal_minutes = 20
    prog.today_focus_minutes = 12
    prog.total_focus_minutes = 180
    print("  · Progress: 245 XP, Level 3, 4-day streak, 12/20 min today")


def _ensure_sessions(student, modules):
    """Ended sessions on UI/UX modules so dashboard focus stats look filled."""
    mod_ids = [m.id for m in modules]
    existing = (
        LearningSession.query.filter(
            LearningSession.student_id == student.id,
            LearningSession.module_id.in_(mod_ids),
        ).count()
    )
    if existing >= 5:
        print(f"  · UI/UX sessions already present ({existing}) — skipping")
        return

    now = datetime.utcnow()
    samples = [
        (modules[0], 72.0, 18),
        (modules[0], 68.0, 22),
        (modules[1], 81.0, 15),
        (modules[1], 75.0, 20),
        (modules[2], 64.0, 12),
    ]
    for i, (mod, focus, mins) in enumerate(samples):
        start = now - timedelta(days=i + 1, hours=2)
        end = start + timedelta(minutes=mins)
        focused = mins * 60 * (focus / 100.0)
        distracted = mins * 60 - focused
        db.session.add(
            LearningSession(
                student_id=student.id,
                module_id=mod.id,
                start_time=start,
                end_time=end,
                is_monitored=True,
                xp_awarded=True,
                focus_metric_version="observed_v1",
                observed_focused_seconds=focused,
                observed_distracted_seconds=distracted,
                unknown_seconds=0.0,
                monitoring_coverage_pct=100.0,
                focus_percentage=focus,
            )
        )
    print(f"  + Added {len(samples)} dummy focus sessions on UI/UX modules")


def seed_ui_screenshots():
    app = create_app()
    with app.app_context():
        print("Screenshot fixture (temporary)")

        user = User.query.filter_by(email=STUDENT_EMAIL).first()
        if not user:
            raise SystemExit(
                f"{STUDENT_EMAIL} missing — start the backend once so default accounts seed."
            )
        user.first_name = "Kalhara"
        user.last_name = user.last_name or "Student"
        print(f"  · User display name → Kalhara ({STUDENT_EMAIL})")

        student = Student.query.filter_by(user_id=user.id).first()
        if not student:
            raise SystemExit("Student profile missing for student@luma.com")
        student.grade_level = GRADE_NAME

        grade = GradeLevel.query.filter_by(name=GRADE_NAME).first()
        if not grade:
            grade = GradeLevel(name=GRADE_NAME)
            db.session.add(grade)
            db.session.flush()

        teacher = _ensure_teacher()

        main = _ensure_subject(
            SUBJECT_TITLE,
            "Design usable digital products — research, wireframes, prototypes, and critique.",
            grade.id,
            teacher,
        )
        modules = _ensure_modules(main)

        # Wipe enrollments then re-add in order so continue card = UI/UX Engineering
        for e in Enrollment.query.filter_by(student_id=student.id).all():
            db.session.delete(e)
        db.session.flush()

        keep_ids = []
        # DEMO: filler subjects disabled — only real subjects for the doctor demo.
        # To bring them back, re-add:
        #     + [(x["title"], x["description"]) for x in EXTRA_SUBJECTS]
        for i, (sub_title, sub_desc) in enumerate(
            [(SUBJECT_TITLE, main.description)]
        ):
            if sub_title == SUBJECT_TITLE:
                sub = main
            else:
                sub = _ensure_subject(sub_title, sub_desc, grade.id, teacher)
                if not Module.query.filter_by(subject_id=sub.id).first():
                    db.session.add(
                        Module(
                            title="Overview",
                            description=sub_desc,
                            subject_id=sub.id,
                            sequence_order=1,
                        )
                    )
            _ensure_enrollment(
                student, sub, enrolled_at=datetime(2026, 1, 1 + i, 9, 0, 0)
            )
            keep_ids.append(sub.id)

        print(f"  · Enrollments reset ({len(keep_ids)}) — UI/UX first for screenshots")
        # DEMO: dummy XP/streak and fake focus sessions disabled so dashboards
        # show only real monitored data. Uncomment for screenshot fixtures.
        # _ensure_progress(student)
        # _ensure_sessions(student, modules)

        db.session.commit()
        print(
            "Done.\n"
            "  Student: student@luma.com / Student123!  → Kalhara\n"
            "  Teacher: teacher@luma.com / Teacher123!  → Mrs. Nayanaransi"
        )


if __name__ == "__main__":
    seed_ui_screenshots()
