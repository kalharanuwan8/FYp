"""
DSM-5 inattention behavioural proxies (record-only).

Each indicator is counted independently. There is no single overall
"distracted" label. Camera fusion is only one source under DSM-2 and
applies during monitored video/lesson sessions.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional

from app.db_models import (
    BehaviourEvent,
    DistractionEvent,
    InterventionLog,
    LearningSession,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
    StudentProgress,
)
from app.extensions import db

# Tunable constants (engineering parameters, not clinical cutoffs).
IDLE_MIN_SECONDS = 15.0
CARELESS_EASY_STREAK = 3
HINT_ALL_MIN_QUESTIONS = 3
RANDOM_ERROR_RATE = 0.70
RANDOM_MEDIAN_MS = 5000
FORGETFUL_LOOKBACK_DAYS = 7  # excludes today

INDICATOR_LABELS = {
    "dsm1_sustain": "Difficulty sustaining attention (idle)",
    "dsm2_external": "Easily distracted by external stimuli",
    "dsm3_finish": "Fails to finish / overtime on quizzes",
    "dsm4_careless": "Careless mistakes on easy items",
    "dsm5_hints": "Does not seem to listen (hints on all questions)",
    "dsm6_effort": "Avoids sustained mental effort (fast + high error)",
    "dsm7_forgetful": "Forgetful in daily activities (missed study goal)",
}


def _window_start(days: int, now: Optional[datetime] = None) -> datetime:
    now = now or datetime.utcnow()
    return now - timedelta(days=int(days))


def _idle_count(student_id: int, since: datetime) -> Dict[str, Any]:
    rows = (
        BehaviourEvent.query.filter(
            BehaviourEvent.student_id == student_id,
            BehaviourEvent.indicator == "idle",
            BehaviourEvent.started_at >= since,
            BehaviourEvent.duration_seconds >= IDLE_MIN_SECONDS,
        )
        .order_by(BehaviourEvent.started_at.desc())
        .all()
    )
    return {
        "count": len(rows),
        "evidence": [
            {
                "context": r.context,
                "duration_seconds": r.duration_seconds,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "quiz_attempt_id": r.quiz_attempt_id,
                "module_content_id": r.module_content_id,
            }
            for r in rows[:20]
        ],
    }


def _external_stimuli(student_id: int, since: datetime) -> Dict[str, Any]:
    sessions = LearningSession.query.filter(
        LearningSession.student_id == student_id,
        LearningSession.start_time >= since,
    ).all()
    session_ids = [s.id for s in sessions]
    camera_n = 0
    noise_n = 0
    if session_ids:
        camera_n = DistractionEvent.query.filter(
            DistractionEvent.session_id.in_(session_ids),
            DistractionEvent.verdict == "distracted",
            DistractionEvent.started_at >= since,
        ).count()
        noise_n = InterventionLog.query.filter(
            InterventionLog.session_id.in_(session_ids),
            InterventionLog.intervention_type == "environment_noise_notice",
            InterventionLog.triggered_at >= since,
        ).count()
    return {
        "count": int(camera_n) + int(noise_n),
        "evidence": {
            "camera_distracted_episodes": int(camera_n),
            "noise_notices": int(noise_n),
            "note": "Camera episodes apply during monitored video/lesson sessions only.",
        },
    }


def _attempt_duration_minutes(attempt: QuizAttempt) -> Optional[float]:
    if not attempt.started_at:
        return None
    end = attempt.completed_at or datetime.utcnow()
    return max(0.0, (end - attempt.started_at).total_seconds() / 60.0)


def _fails_to_finish(student_id: int, since: datetime, now: datetime) -> Dict[str, Any]:
    attempts = QuizAttempt.query.filter(
        QuizAttempt.student_id == student_id,
        QuizAttempt.started_at >= since,
    ).all()
    hits: List[Dict[str, Any]] = []
    for att in attempts:
        quiz = db.session.get(Quiz, att.quiz_id)
        limit = quiz.time_limit_minutes if quiz else None
        if limit is None or limit <= 0:
            continue
        elapsed = _attempt_duration_minutes(att)
        if elapsed is None:
            continue
        incomplete_overtime = att.completed_at is None and elapsed > float(limit)
        completed_overtime = (
            att.completed_at is not None and elapsed > float(limit)
        )
        if incomplete_overtime or completed_overtime:
            hits.append(
                {
                    "attempt_id": att.id,
                    "quiz_id": att.quiz_id,
                    "time_limit_minutes": limit,
                    "elapsed_minutes": round(elapsed, 2),
                    "completed": att.completed_at is not None,
                }
            )
    return {"count": len(hits), "evidence": hits[:20]}


def _careless_mistakes(student_id: int, since: datetime) -> Dict[str, Any]:
    attempts = (
        QuizAttempt.query.filter(
            QuizAttempt.student_id == student_id,
            QuizAttempt.started_at >= since,
            QuizAttempt.completed_at.isnot(None),
        ).all()
    )
    hits: List[Dict[str, Any]] = []
    for att in attempts:
        answers = (
            QuizAnswer.query.filter_by(attempt_id=att.id)
            .order_by(QuizAnswer.answered_at.asc(), QuizAnswer.id.asc())
            .all()
        )
        streak = 0
        max_streak = 0
        for ans in answers:
            q = db.session.get(QuizQuestion, ans.question_id)
            is_easy = q is not None and (q.difficulty or "medium").lower() == "easy"
            if is_easy and not ans.is_correct:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        if max_streak >= CARELESS_EASY_STREAK:
            hits.append(
                {
                    "attempt_id": att.id,
                    "quiz_id": att.quiz_id,
                    "max_easy_error_streak": max_streak,
                }
            )
    return {"count": len(hits), "evidence": hits[:20]}


def _hints_all_questions(student_id: int, since: datetime) -> Dict[str, Any]:
    attempts = (
        QuizAttempt.query.filter(
            QuizAttempt.student_id == student_id,
            QuizAttempt.started_at >= since,
            QuizAttempt.completed_at.isnot(None),
        ).all()
    )
    hits: List[Dict[str, Any]] = []
    for att in attempts:
        quiz = db.session.get(Quiz, att.quiz_id)
        n_q = len(quiz.questions) if quiz else 0
        if n_q < HINT_ALL_MIN_QUESTIONS:
            continue
        answers = QuizAnswer.query.filter_by(attempt_id=att.id).all()
        by_q = {a.question_id: a for a in answers}
        if len(by_q) < n_q:
            continue
        if all(bool(a.hint_used) for a in by_q.values()):
            hits.append(
                {
                    "attempt_id": att.id,
                    "quiz_id": att.quiz_id,
                    "questions": n_q,
                    "hints_used": n_q,
                }
            )
    return {"count": len(hits), "evidence": hits[:20]}


def _avoids_effort(student_id: int, since: datetime) -> Dict[str, Any]:
    attempts = (
        QuizAttempt.query.filter(
            QuizAttempt.student_id == student_id,
            QuizAttempt.started_at >= since,
            QuizAttempt.completed_at.isnot(None),
        ).all()
    )
    hits: List[Dict[str, Any]] = []
    for att in attempts:
        answers = QuizAnswer.query.filter_by(attempt_id=att.id).all()
        if not answers:
            continue
        n = len(answers)
        wrong = sum(1 for a in answers if not a.is_correct)
        error_rate = wrong / float(n)
        times = [a.response_ms for a in answers if a.response_ms is not None and a.response_ms >= 0]
        if not times:
            continue
        med = float(median(times))
        if error_rate >= RANDOM_ERROR_RATE and med < RANDOM_MEDIAN_MS:
            hits.append(
                {
                    "attempt_id": att.id,
                    "quiz_id": att.quiz_id,
                    "error_rate": round(error_rate, 3),
                    "median_response_ms": round(med, 1),
                    "n_answers": n,
                }
            )
    return {"count": len(hits), "evidence": hits[:20]}


def _forgetful_days(student_id: int, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.utcnow()
    today = now.date()
    progress = StudentProgress.query.filter_by(student_id=student_id).first()
    goal = int(progress.daily_goal_minutes) if progress else 20
    missed: List[Dict[str, Any]] = []
    for i in range(1, FORGETFUL_LOOKBACK_DAYS + 1):
        day = today - timedelta(days=i)
        day_start = datetime.combine(day, datetime.min.time())
        day_end = day_start + timedelta(days=1)
        sessions = LearningSession.query.filter(
            LearningSession.student_id == student_id,
            LearningSession.start_time >= day_start,
            LearningSession.start_time < day_end,
            LearningSession.end_time.isnot(None),
        ).all()
        minutes = 0.0
        for s in sessions:
            if s.start_time and s.end_time and s.end_time > s.start_time:
                minutes += (s.end_time - s.start_time).total_seconds() / 60.0
        if minutes < float(goal):
            missed.append(
                {
                    "date": day.isoformat(),
                    "minutes": round(minutes, 1),
                    "daily_goal_minutes": goal,
                }
            )
    return {"count": len(missed), "evidence": missed}


def build_dsm_profile(
    student_id: int,
    days: int = 7,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Per-indicator profile for the last ``days`` (DSM-7 uses fixed 7-day lookback)."""
    now = now or datetime.utcnow()
    since = _window_start(days, now)
    blocks = {
        "dsm1_sustain": _idle_count(student_id, since),
        "dsm2_external": _external_stimuli(student_id, since),
        "dsm3_finish": _fails_to_finish(student_id, since, now),
        "dsm4_careless": _careless_mistakes(student_id, since),
        "dsm5_hints": _hints_all_questions(student_id, since),
        "dsm6_effort": _avoids_effort(student_id, since),
        "dsm7_forgetful": _forgetful_days(student_id, now),
    }
    indicators = []
    for key, block in blocks.items():
        indicators.append(
            {
                "id": key,
                "label": INDICATOR_LABELS[key],
                "count": block["count"],
                "evidence": block["evidence"],
            }
        )
    return {
        "student_id": student_id,
        "window_days": int(days),
        "generated_at": now.isoformat() + "Z",
        "disclaimer": (
            "Behavioural proxies aligned with DSM-5 inattention descriptions. "
            "Not a clinical diagnosis."
        ),
        "indicators": indicators,
        "constants": {
            "idle_min_seconds": IDLE_MIN_SECONDS,
            "careless_easy_streak": CARELESS_EASY_STREAK,
            "hint_all_min_questions": HINT_ALL_MIN_QUESTIONS,
            "random_error_rate": RANDOM_ERROR_RATE,
            "random_median_ms": RANDOM_MEDIAN_MS,
            "forgetful_lookback_days": FORGETFUL_LOOKBACK_DAYS,
        },
    }
