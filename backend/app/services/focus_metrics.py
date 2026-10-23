"""Focus percentage helpers — observed_v1 coverage (Phase 2A)."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional, Sequence

from app.db_models import LearningSession, MonitoringObservation
from app.services.observation_coverage import (
    FOCUS_METRIC_VERSION,
    LEGACY_METRIC_VERSION,
    ObservationPoint,
    CoverageResult,
    compute_coverage_from_observations,
    empty_coverage,
)

DB_DISTRACTED = "distracted"


def observations_for_session(session_id: int) -> List[ObservationPoint]:
    rows = (
        MonitoringObservation.query.filter_by(session_id=session_id)
        .order_by(MonitoringObservation.observed_at.asc())
        .all()
    )
    return [
        ObservationPoint(observed_at=r.observed_at, state=r.state) for r in rows
    ]


def compute_session_coverage(
    session: LearningSession, now_dt: Optional[datetime] = None
) -> CoverageResult:
    """Compute observed_v1 coverage from persisted MonitoringObservation rows."""
    now_dt = now_dt or datetime.utcnow()
    end = session.end_time or now_dt
    start = session.start_time
    if not start:
        return empty_coverage(0.0)
    if end <= start:
        return empty_coverage(0.0)
    points = observations_for_session(session.id)
    return compute_coverage_from_observations(
        start_time=start, end_time=end, observations=points
    )


def compute_session_focus_percentage(
    session: LearningSession, now_dt: Optional[datetime] = None
) -> Optional[float]:
    """
    observed_v1 focus % over valid observed time, or None if unavailable.

    Prefer persisted snapshot when the session already stores observed_v1.
    Never invent coverage for legacy sessions that never stored observations.
    """
    if session.focus_metric_version == FOCUS_METRIC_VERSION:
        return session.focus_percentage

    # Live / just-ended sessions with observation rows
    has_obs = (
        MonitoringObservation.query.filter_by(session_id=session.id).first() is not None
    )
    if has_obs or session.focus_metric_version is None:
        # If ended before Phase 2A with no observations, do not fake coverage.
        if session.end_time and not has_obs and session.focus_metric_version is None:
            # Legacy session: no observations stored — unavailable for observed_v1.
            if session.observed_focused_seconds is None:
                return None
        cov = compute_session_coverage(session, now_dt=now_dt)
        return cov.focus_percentage
    return None


def legacy_wallclock_focus_percentage(
    session: LearningSession, now_dt: Optional[datetime] = None
) -> float:
    """
    Pre-Phase-2A metric: wall-clock minus distracted episodes (gaps count as focused).
    Kept for documentation/comparison only — not mixed into observed_v1 aggregates.
    """
    from app.db_models import DistractionEvent

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


def apply_coverage_to_session(
    session: LearningSession, coverage: CoverageResult
) -> None:
    """Persist observed_v1 snapshot onto the session row (caller commits)."""
    session.focus_metric_version = FOCUS_METRIC_VERSION
    session.observed_focused_seconds = coverage.observed_focused_seconds
    session.observed_distracted_seconds = coverage.observed_distracted_seconds
    session.unknown_seconds = coverage.unknown_seconds
    session.monitoring_coverage_pct = coverage.monitoring_coverage_pct
    session.focus_percentage = coverage.focus_percentage


def average_focus_percentage(
    sessions: Iterable[LearningSession], now_dt: Optional[datetime] = None
) -> Optional[float]:
    """
    Average observed_v1 focus % across sessions that have a usable value.
    Legacy sessions without coverage are excluded (not silently mixed).
    Returns None if no session contributes a numeric focus %.
    """
    vals: List[float] = []
    for s in sessions:
        if s.focus_metric_version == FOCUS_METRIC_VERSION and s.focus_percentage is not None:
            vals.append(float(s.focus_percentage))
            continue
        pct = compute_session_focus_percentage(s, now_dt=now_dt)
        if pct is not None:
            vals.append(float(pct))
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def average_coverage_pct(
    sessions: Sequence[LearningSession],
) -> Optional[float]:
    vals = [
        float(s.monitoring_coverage_pct)
        for s in sessions
        if s.focus_metric_version == FOCUS_METRIC_VERSION
        and s.monitoring_coverage_pct is not None
    ]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)
