"""
Hide or restore the screenshot dummy data (from seed_ui_screenshots.py) so the
demo shows only real monitored data. Nothing is lost: every row that is taken
out is saved to demo_archive/dummy_data_archive.json and put back by `restore`.

  python demo_dummy_data.py hide              # preview only
  python demo_dummy_data.py hide --apply      # archive + hide
  python demo_dummy_data.py restore --apply   # put everything back

What counts as dummy data:
  - focus sessions that claim 100% observed coverage but have no monitoring
    observations and no distraction episodes (seeded, never monitored)
  - the seeded XP / focus minutes / streak on student@luma.com
  - badges that were only earned because of those seeded numbers
  - the filler subjects "Interaction Design Studio" and "Visual Systems & Typography"
    (archived with Subject.is_archived, not deleted)
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime

from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.db_models import LearningSession, Student, Subject, User
from app.db_models.gamification import Badge, StudentBadge, StudentProgress
from app.services.gamification_service import _level_for_xp

STUDENT_EMAIL = "student@luma.com"
FILLER_SUBJECTS = ["Interaction Design Studio", "Visual Systems & Typography"]
# Amounts written by seed_ui_screenshots._ensure_progress
SEEDED_XP = 245
SEEDED_TOTAL_FOCUS_MINUTES = 180

ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_archive")
ARCHIVE_PATH = os.path.join(ARCHIVE_DIR, "dummy_data_archive.json")

SESSION_COLUMNS = [
    "id", "student_id", "module_content_id", "started_at", "ended_at", "was_monitored",
    "created_at", "xp_awarded", "focus_metric_version", "observed_focused_seconds",
    "observed_distracted_seconds", "unknown_seconds", "monitoring_coverage_pct",
    "focus_percentage",
]
PROGRESS_FIELDS = ["xp", "level", "current_streak", "longest_streak", "total_focus_minutes"]


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Cannot serialise {type(value)}")


def _parse_dt(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _find_dummy_session_ids():
    rows = db.session.execute(text("""
        SELECT s.id FROM sessions s
        WHERE s.focus_metric_version = 'observed_v1'
          AND s.monitoring_coverage_pct = 100
          AND NOT EXISTS (SELECT 1 FROM monitoring_observations o WHERE o.session_id = s.id)
          AND NOT EXISTS (SELECT 1 FROM distraction_events d WHERE d.session_id = s.id)
          AND NOT EXISTS (SELECT 1 FROM intervention_logs i WHERE i.session_id = s.id)
        ORDER BY s.id
    """)).scalars().all()
    return list(rows)


def _demo_student():
    user = User.query.filter_by(email=STUDENT_EMAIL).first()
    return Student.query.filter_by(user_id=user.id).first() if user else None


def hide(apply: bool):
    if os.path.exists(ARCHIVE_PATH):
        raise SystemExit(f"Already hidden — archive exists at {ARCHIVE_PATH}. Run `restore` first.")

    session_ids = _find_dummy_session_ids()
    sessions = []
    if session_ids:
        cols = ", ".join(SESSION_COLUMNS)
        sessions = [
            dict(r._mapping)
            for r in db.session.execute(
                text(f"SELECT {cols} FROM sessions WHERE id = ANY(:ids) ORDER BY id"),
                {"ids": session_ids},
            )
        ]

    student = _demo_student()
    progress = StudentProgress.query.filter_by(student_id=student.id).first() if student else None
    progress_before = {f: getattr(progress, f) for f in PROGRESS_FIELDS} if progress else None
    progress_after = None
    badges = []
    if progress:
        xp = max(0, progress.xp - SEEDED_XP)
        total = max(0, progress.total_focus_minutes - SEEDED_TOTAL_FOCUS_MINUTES)
        current = min(progress.current_streak, 1) if progress.current_streak else 0
        progress_after = {
            "xp": xp,
            "level": _level_for_xp(xp),
            "current_streak": current,
            "longest_streak": current,
            "total_focus_minutes": total,
        }
        unearned = []
        if total < 60:
            unearned.append("focus_60")
        if progress_after["longest_streak"] < 3:
            unearned.append("streak_3")
        if progress_after["longest_streak"] < 7:
            unearned.append("streak_7")
        for sb in StudentBadge.query.filter_by(student_id=student.id).all():
            badge = db.session.get(Badge, sb.badge_id)
            if badge and badge.code in unearned:
                badges.append({
                    "id": sb.id, "student_id": sb.student_id, "badge_id": sb.badge_id,
                    "code": badge.code, "earned_at": sb.earned_at,
                })

    subjects = Subject.query.filter(Subject.title.in_(FILLER_SUBJECTS), Subject.is_archived.is_(False)).all()

    print("Dummy data to hide:")
    print(f"  sessions:  {[s['id'] for s in sessions]}")
    print(f"  progress:  {progress_before} -> {progress_after}")
    print(f"  badges:    {[b['code'] for b in badges]}")
    print(f"  subjects:  {[s.title for s in subjects]} (set is_archived=True)")
    if not apply:
        print("\nPreview only. Re-run with --apply to archive and hide.")
        return

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    archive = {
        "created_at": datetime.utcnow(),
        "sessions": sessions,
        "progress": {"student_id": student.id, "before": progress_before} if progress else None,
        "badges": badges,
        "subject_ids": [s.id for s in subjects],
    }
    with open(ARCHIVE_PATH, "w", encoding="utf-8") as fh:
        json.dump(archive, fh, indent=2, default=_json_default)

    if session_ids:
        LearningSession.query.filter(LearningSession.id.in_(session_ids)).delete(synchronize_session=False)
    if progress:
        for field, value in progress_after.items():
            setattr(progress, field, value)
    if badges:
        StudentBadge.query.filter(StudentBadge.id.in_([b["id"] for b in badges])).delete(synchronize_session=False)
    for s in subjects:
        s.is_archived = True
    db.session.commit()
    print(f"\nHidden. Archive saved to {ARCHIVE_PATH}")


def restore(apply: bool):
    if not os.path.exists(ARCHIVE_PATH):
        raise SystemExit("Nothing to restore — no archive found.")
    with open(ARCHIVE_PATH, encoding="utf-8") as fh:
        archive = json.load(fh)

    print("Restoring:")
    print(f"  sessions:  {[s['id'] for s in archive['sessions']]}")
    print(f"  progress:  {archive['progress']}")
    print(f"  badges:    {[b['code'] for b in archive['badges']]}")
    print(f"  subjects:  {archive['subject_ids']} (set is_archived=False)")
    if not apply:
        print("\nPreview only. Re-run with --apply to restore.")
        return

    for row in archive["sessions"]:
        for key in ("started_at", "ended_at", "created_at"):
            row[key] = _parse_dt(row[key])
        cols = ", ".join(SESSION_COLUMNS)
        params = ", ".join(f":{c}" for c in SESSION_COLUMNS)
        db.session.execute(text(f"INSERT INTO sessions ({cols}) VALUES ({params})"), row)

    if archive["progress"]:
        progress = StudentProgress.query.filter_by(student_id=archive["progress"]["student_id"]).first()
        if progress:
            for field, value in archive["progress"]["before"].items():
                setattr(progress, field, value)

    for b in archive["badges"]:
        db.session.add(StudentBadge(
            id=b["id"], student_id=b["student_id"], badge_id=b["badge_id"], earned_at=_parse_dt(b["earned_at"]),
        ))

    for subject_id in archive["subject_ids"]:
        subject = db.session.get(Subject, subject_id)
        if subject:
            subject.is_archived = False

    db.session.commit()
    os.replace(ARCHIVE_PATH, ARCHIVE_PATH.replace(".json", f".restored-{datetime.utcnow():%Y%m%d%H%M%S}.json"))
    print("\nRestored.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["hide", "restore"])
    parser.add_argument("--apply", action="store_true", help="make the change (default is a preview)")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        (hide if args.action == "hide" else restore)(args.apply)
