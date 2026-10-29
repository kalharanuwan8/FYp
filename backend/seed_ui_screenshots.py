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
    MonitoringObservation,
    DistractionEvent,
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


def _delete_sessions(session_ids):
    """Remove sessions and dependent rows (events / observations) safely."""
    ids = [int(i) for i in session_ids if i is not None]
    if not ids:
        return
    # Intervention logs reference distraction_events — delete logs first.
    db.session.execute(
        text("DELETE FROM intervention_logs WHERE session_id = ANY(:ids)"),
        {"ids": ids},
    )
    DistractionEvent.query.filter(DistractionEvent.session_id.in_(ids)).delete(
        synchronize_session=False
    )
    MonitoringObservation.query.filter(
        MonitoringObservation.session_id.in_(ids)
    ).delete(synchronize_session=False)
    # Optional FKs — null rather than delete learner quiz/remediation history
    db.session.execute(
        text("UPDATE quiz_attempts SET session_id = NULL WHERE session_id = ANY(:ids)"),
        {"ids": ids},
    )
    db.session.execute(
        text(
            "UPDATE remediation_events SET session_id = NULL WHERE session_id = ANY(:ids)"
        ),
        {"ids": ids},
    )
    LearningSession.query.filter(LearningSession.id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.flush()


def _add_session(
    student,
    module,
    *,
    days_ago: int,
    duration_sec: float,
    focused: float,
    distracted: float,
    unknown: float,
    coverage: float,
    focus_pct,
):
    """One ended observed_v1 session (focus_pct may be None = unavailable)."""
    start = datetime.utcnow() - timedelta(days=days_ago, hours=2)
    end = start + timedelta(seconds=duration_sec)
    db.session.add(
        LearningSession(
            student_id=student.id,
            module_id=module.id,
            start_time=start,
            end_time=end,
            is_monitored=True,
            xp_awarded=True,
            focus_metric_version="observed_v1",
            observed_focused_seconds=focused,
            observed_distracted_seconds=distracted,
            unknown_seconds=unknown,
            monitoring_coverage_pct=coverage,
            focus_percentage=focus_pct,
        )
    )


def _ensure_sessions(student, modules):
    """
    Demo sessions for analytics screenshot:
      - UI/UX: focus + coverage both visible (chapter6 AN-01 style + variants)
      Values mirror analytics_fixtures.json where noted.
    """
    mod_ids = [m.id for m in modules]
    # Drop prior screenshot fixture sessions on these modules so re-runs refresh numbers
    old_ids = [
        row.id
        for row in LearningSession.query.filter(
            LearningSession.student_id == student.id,
            LearningSession.module_id.in_(mod_ids),
        ).all()
    ]
    _delete_sessions(old_ids)

    # AN-01: focused 8, distracted 2, unknown 10 → focus 80%, coverage 50%
    _add_session(
        student,
        modules[0],
        days_ago=1,
        duration_sec=20.0,
        focused=8.0,
        distracted=2.0,
        unknown=10.0,
        coverage=50.0,
        focus_pct=80.0,
    )
    # Strong coverage / focus (AN-04-like scaled to a longer lesson)
    _add_session(
        student,
        modules[1],
        days_ago=2,
        duration_sec=900.0,
        focused=720.0,
        distracted=90.0,
        unknown=90.0,
        coverage=90.0,
        focus_pct=88.9,
    )
    _add_session(
        student,
        modules[1],
        days_ago=3,
        duration_sec=1200.0,
        focused=840.0,
        distracted=240.0,
        unknown=120.0,
        coverage=90.0,
        focus_pct=77.8,
    )
    _add_session(
        student,
        modules[2],
        days_ago=4,
        duration_sec=600.0,
        focused=420.0,
        distracted=120.0,
        unknown=60.0,
        coverage=90.0,
        focus_pct=77.8,
    )
    # AN-02: focus 0% with coverage 60% (still a numeric focus, not unavailable)
    _add_session(
        student,
        modules[0],
        days_ago=5,
        duration_sec=10.0,
        focused=0.0,
        distracted=6.0,
        unknown=4.0,
        coverage=60.0,
        focus_pct=0.0,
    )
    print(f"  + Added 5 dummy focus+coverage sessions on UI/UX modules")


def _ensure_unavailable_focus_subject(student, teacher, grade_id):
    """
    Second enrolled subject where every session has focus_percentage=null
    (all UNKNOWN → focus unavailable) but coverage is still shown (0%).
    Mirrors chapter6 AN-03 / AN-05.
    """
    title = "Camera Calibration Labs"
    subject = _ensure_subject(
        title,
        "Low-light / no-face fixture — focus unavailable, coverage recorded.",
        grade_id,
        teacher,
    )
    mod = Module.query.filter_by(subject_id=subject.id, title="No-face coverage check").first()
    if not mod:
        mod = Module(
            title="No-face coverage check",
            description="All-UNKNOWN observed_v1 sessions for screenshot.",
            subject_id=subject.id,
            sequence_order=1,
        )
        db.session.add(mod)
        db.session.flush()

    old_ids = [
        row.id
        for row in LearningSession.query.filter(
            LearningSession.student_id == student.id,
            LearningSession.module_id == mod.id,
        ).all()
    ]
    _delete_sessions(old_ids)

    # AN-03: 30s all unknown → coverage 0%, focus null
    _add_session(
        student,
        mod,
        days_ago=2,
        duration_sec=30.0,
        focused=0.0,
        distracted=0.0,
        unknown=30.0,
        coverage=0.0,
        focus_pct=None,
    )
    # AN-05: 60s all unknown
    _add_session(
        student,
        mod,
        days_ago=6,
        duration_sec=60.0,
        focused=0.0,
        distracted=0.0,
        unknown=60.0,
        coverage=0.0,
        focus_pct=None,
    )
    _ensure_enrollment(student, subject, enrolled_at=datetime(2026, 1, 3, 9, 0, 0))
    print(f"  + Subject '{title}' with focus unavailable · 0% coverage sessions")
    return subject


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
        # Screenshot fixture: progress + focus/coverage sessions + unavailable focus subject
        _ensure_progress(student)
        _ensure_sessions(student, modules)
        unavailable = _ensure_unavailable_focus_subject(student, teacher, grade.id)
        keep_ids.append(unavailable.id)

        db.session.commit()
        print(
            "Done.\n"
            "  Student: student@luma.com / Student123!  → Kalhara\n"
            "  Teacher: teacher@luma.com / Teacher123!  → Mrs. Nayanaransi\n"
            "  Open http://localhost:5173/student/analytics for the screenshot\n"
            "  (Average focus + Monitoring coverage stats; Camera Calibration Labs shows focus unavailable)"
        )


if __name__ == "__main__":
    seed_ui_screenshots()
