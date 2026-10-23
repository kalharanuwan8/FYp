"""Award XP, update streaks, and unlock badges for student focus sessions."""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from app.extensions import db
from app.db_models.gamification import Badge, StudentBadge, StudentProgress

# XP rates
XP_PER_FOCUS_MINUTE = 2
XP_PER_CORRECT_ANSWER = 10
XP_QUIZ_ACE_BONUS = 25
XP_MODULE_COMPLETE = 40

BADGE_DEFS = [
    {
        "code": "first_session",
        "name": "First Focus",
        "description": "Completed your first focus session",
        "icon": "🌱",
    },
    {
        "code": "streak_3",
        "name": "On a Roll",
        "description": "Kept a 3-day focus streak",
        "icon": "🔥",
    },
    {
        "code": "focus_60",
        "name": "Hour Hero",
        "description": "Logged 60 focused minutes in total",
        "icon": "⏱️",
    },
    {
        "code": "quiz_ace",
        "name": "Quiz Ace",
        "description": "Got every answer right on a quiz",
        "icon": "🎯",
    },
    {
        "code": "streak_7",
        "name": "Week Warrior",
        "description": "Kept a 7-day focus streak",
        "icon": "💫",
    },
]


def _ensure_badges():
    for spec in BADGE_DEFS:
        existing = Badge.query.filter_by(code=spec["code"]).first()
        if not existing:
            db.session.add(Badge(**spec))
    db.session.flush()


def get_or_create_progress(student_id: int) -> StudentProgress:
    progress = StudentProgress.query.filter_by(student_id=student_id).first()
    if progress:
        _maybe_reset_today(progress)
        return progress
    progress = StudentProgress(student_id=student_id)
    db.session.add(progress)
    db.session.flush()
    return progress


def _maybe_reset_today(progress: StudentProgress):
    today = date.today()
    if progress.last_active_date and progress.last_active_date < today:
        # Don't wipe streak here — streak update happens on award
        if progress.last_active_date < today:
            # Reset daily counter when calendar day changes
            progress.today_focus_minutes = 0


def _level_for_xp(xp: int) -> int:
    # Soft curve: level 1 at 0, then every ~100 XP * level
    level = 1
    remaining = xp
    while remaining >= level * 100:
        remaining -= level * 100
        level += 1
        if level > 99:
            break
    return level


def _update_streak(progress: StudentProgress, on_date: Optional[date] = None):
    today = on_date or date.today()
    last = progress.last_active_date
    if last == today:
        return
    if last == today - timedelta(days=1):
        progress.current_streak = (progress.current_streak or 0) + 1
    elif last is None or last < today - timedelta(days=1):
        progress.current_streak = 1
    progress.longest_streak = max(progress.longest_streak or 0, progress.current_streak)
    progress.last_active_date = today


def _award_badge(student_id: int, code: str) -> Optional[StudentBadge]:
    _ensure_badges()
    badge = Badge.query.filter_by(code=code).first()
    if not badge:
        return None
    existing = StudentBadge.query.filter_by(
        student_id=student_id, badge_id=badge.id
    ).first()
    if existing:
        return None
    earned = StudentBadge(student_id=student_id, badge_id=badge.id)
    earned.badge = badge
    db.session.add(earned)
    db.session.flush()
    return earned


def _check_milestones(progress: StudentProgress, student_id: int) -> List[StudentBadge]:
    newly = []
    if progress.total_focus_minutes > 0:
        b = _award_badge(student_id, "first_session")
        if b:
            newly.append(b)
    if progress.current_streak >= 3:
        b = _award_badge(student_id, "streak_3")
        if b:
            newly.append(b)
    if progress.current_streak >= 7:
        b = _award_badge(student_id, "streak_7")
        if b:
            newly.append(b)
    if progress.total_focus_minutes >= 60:
        b = _award_badge(student_id, "focus_60")
        if b:
            newly.append(b)
    return newly


def award_session_xp(
    student_id: int,
    *,
    duration_seconds: int = 0,
    focus_percentage: Optional[float] = None,
    observed_focused_seconds: Optional[float] = None,
    commit: bool = True,
) -> dict:
    """
    Award XP after a learning session stops.

    Phase 2A: focused-time XP uses observed_focused_seconds only. Unknown /
    unobserved time does not earn focus XP. A null focus_percentage with zero
    observed focus yields 0 focus minutes (no wall-clock consolation credit).
    """
    progress = get_or_create_progress(student_id)
    if observed_focused_seconds is not None:
        focus_minutes = max(0, int(round(float(observed_focused_seconds) / 60.0)))
    elif focus_percentage is not None:
        # Legacy callers: duration * focus fraction (focus_percentage may be 0)
        focus_frac = max(0.0, min(100.0, float(focus_percentage))) / 100.0
        focus_minutes = max(0, int(round((duration_seconds / 60.0) * focus_frac)))
    else:
        focus_minutes = 0

    xp_gained = focus_minutes * XP_PER_FOCUS_MINUTE
    progress.xp = (progress.xp or 0) + xp_gained
    progress.level = _level_for_xp(progress.xp)
    progress.today_focus_minutes = (progress.today_focus_minutes or 0) + focus_minutes
    progress.total_focus_minutes = (progress.total_focus_minutes or 0) + focus_minutes
    _update_streak(progress)
    new_badges = _check_milestones(progress, student_id)
    if commit:
        db.session.commit()

    return {
        "xp_gained": xp_gained,
        "focus_minutes": focus_minutes,
        "progress": progress.to_dict(),
        "new_badges": [b.to_dict() for b in new_badges],
    }


def award_quiz_xp(
    student_id: int,
    *,
    correct_count: int,
    total_questions: int,
) -> dict:
    progress = get_or_create_progress(student_id)
    xp_gained = max(0, int(correct_count)) * XP_PER_CORRECT_ANSWER
    ace = total_questions > 0 and correct_count == total_questions
    new_badges = []
    if ace:
        xp_gained += XP_QUIZ_ACE_BONUS
        b = _award_badge(student_id, "quiz_ace")
        if b:
            new_badges.append(b)

    progress.xp = (progress.xp or 0) + xp_gained
    progress.level = _level_for_xp(progress.xp)
    _update_streak(progress)
    new_badges.extend(_check_milestones(progress, student_id))
    db.session.commit()

    return {
        "xp_gained": xp_gained,
        "quiz_ace": ace,
        "progress": progress.to_dict(),
        "new_badges": [b.to_dict() for b in new_badges],
    }


def award_module_complete(student_id: int) -> dict:
    progress = get_or_create_progress(student_id)
    progress.xp = (progress.xp or 0) + XP_MODULE_COMPLETE
    progress.level = _level_for_xp(progress.xp)
    _update_streak(progress)
    new_badges = _check_milestones(progress, student_id)
    db.session.commit()
    return {
        "xp_gained": XP_MODULE_COMPLETE,
        "progress": progress.to_dict(),
        "new_badges": [b.to_dict() for b in new_badges],
    }


def list_student_badges(student_id: int) -> list:
    _ensure_badges()
    rows = (
        StudentBadge.query.filter_by(student_id=student_id)
        .order_by(StudentBadge.earned_at.desc())
        .all()
    )
    return [r.to_dict() for r in rows]


def get_progress_payload(student_id: int) -> dict:
    _ensure_badges()
    progress = get_or_create_progress(student_id)
    badges = list_student_badges(student_id)
    all_badges = [b.to_dict() for b in Badge.query.order_by(Badge.id).all()]
    earned_codes = {b["badge"]["code"] for b in badges if b.get("badge")}
    return {
        **progress.to_dict(),
        "badges": badges,
        "badge_catalog": [
            {**b, "earned": b["code"] in earned_codes} for b in all_badges
        ],
    }
