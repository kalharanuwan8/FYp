"""Focus percentage helpers based on distracted-episode wall time."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from app.db_models import DistractionEvent, LearningSession

DB_DISTRACTED = "distracted"


def compute_session_focus_percentage(
    session: LearningSession, now_dt: Optional[datetime] = None
) -> float:
    """Focus % = share of session wall time not covered by distracted episodes."""
    now_dt = now_dt or datetime.utcnow()
    end = session.end_time or now_dt
    start = session.start_time
    if not start or end <= start:
        return 100.0

    total = (end - start).total_seconds()
    events = DistractionEvent.query.filter_by(
        session_id=session.id, verdict=DB_DISTRACTED
    ).all()
    distracted = 0.0
    for event in events:
        e_start = event.started_at or start
        e_end = event.ended_at or end
        if e_start < start:
            e_start = start
        if e_end > end:
            e_end = end
        if e_end > e_start:
            distracted += (e_end - e_start).total_seconds()
    distracted = min(distracted, total)
    return round(max(0.0, ((total - distracted) / total) * 100.0), 1)


def average_focus_percentage(
    sessions: Iterable[LearningSession], now_dt: Optional[datetime] = None
) -> float:
    sessions = list(sessions)
    if not sessions:
        return 0.0
    vals = [compute_session_focus_percentage(s, now_dt=now_dt) for s in sessions]
    return round(sum(vals) / len(vals), 1)
