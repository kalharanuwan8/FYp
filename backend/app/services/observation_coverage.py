"""
Observation-interval coverage accounting (focus_metric_version = observed_v1).

Normative rules: dev/OBSERVATION_COVERAGE_SPEC.md
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple

FOCUS_METRIC_VERSION = "observed_v1"
LEGACY_METRIC_VERSION = "legacy_wallclock_v0"

# Accounting constants (seconds) — not ML window sizes.
# T_SUPPORT: max forward coverage of one valid observation; also episode
#            continuity limit (gap > T_SUPPORT breaks continuous distraction).
# T_GAP_MAX: interrupted-monitoring detector only (does not extend coverage
#            or keep episodes continuous across unknown remainders).
T_SUPPORT = 3.0
T_GAP_MAX = 5.0

STATE_FOCUSED = "FOCUSED"
STATE_DISTRACTED = "DISTRACTED"
STATE_UNKNOWN = "UNKNOWN"
VALID_STATES = frozenset({STATE_FOCUSED, STATE_DISTRACTED})


def is_interrupted_monitoring_gap(gap_seconds: float, t_gap_max: float = T_GAP_MAX) -> bool:
    """True when a sample-to-sample gap exceeds the interrupted-monitoring threshold."""
    return float(gap_seconds) > float(t_gap_max)


@dataclass(frozen=True)
class ObservationPoint:
    observed_at: datetime
    state: str  # FOCUSED | DISTRACTED | UNKNOWN


@dataclass
class CoverageResult:
    observed_focused_seconds: float
    observed_distracted_seconds: float
    unknown_seconds: float
    monitoring_coverage_pct: float
    focus_percentage: Optional[float]  # null when no valid observed time
    focus_metric_version: str = FOCUS_METRIC_VERSION
    session_duration_seconds: float = 0.0

    def as_dict(self) -> dict:
        return {
            "observed_focused_seconds": round(self.observed_focused_seconds, 3),
            "observed_distracted_seconds": round(self.observed_distracted_seconds, 3),
            "unknown_seconds": round(self.unknown_seconds, 3),
            "monitoring_coverage_pct": round(self.monitoring_coverage_pct, 1),
            "focus_percentage": (
                None
                if self.focus_percentage is None
                else round(self.focus_percentage, 1)
            ),
            "focus_metric_version": self.focus_metric_version,
            "session_duration_seconds": round(self.session_duration_seconds, 3),
        }


def _as_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def compute_coverage_from_observations(
    *,
    start_time: datetime,
    end_time: datetime,
    observations: Sequence[ObservationPoint],
    t_support: float = T_SUPPORT,
    t_gap_max: float = T_GAP_MAX,
) -> CoverageResult:
    """
    Attribute session wall time into focused / distracted / unknown per the spec.

    Does not bridge gaps longer than t_support with an assumed state.
    ``t_gap_max`` is accepted for API symmetry with the spec but does not
    change attribution lengths (use ``is_interrupted_monitoring_gap``).
    """
    _ = t_gap_max  # interrupted-monitoring threshold only — see spec §3.3
    start = _as_utc_naive(start_time)
    end = _as_utc_naive(end_time)
    if end <= start:
        return CoverageResult(
            observed_focused_seconds=0.0,
            observed_distracted_seconds=0.0,
            unknown_seconds=0.0,
            monitoring_coverage_pct=0.0,
            focus_percentage=None,
            session_duration_seconds=0.0,
        )

    duration = (end - start).total_seconds()
    ordered = sorted(
        (
            ObservationPoint(_as_utc_naive(o.observed_at), o.state.upper().strip())
            for o in observations
            if o.observed_at is not None
        ),
        key=lambda o: o.observed_at,
    )
    # Clamp observation times into [start, end]
    clipped: List[ObservationPoint] = []
    for o in ordered:
        t = o.observed_at
        if t < start:
            t = start
        if t > end:
            continue
        clipped.append(ObservationPoint(t, o.state))

    focused = 0.0
    distracted = 0.0

    def _add(state: str, seconds: float) -> None:
        nonlocal focused, distracted
        if seconds <= 0:
            return
        if state == STATE_FOCUSED:
            focused += seconds
        elif state == STATE_DISTRACTED:
            distracted += seconds

    for i, obs in enumerate(clipped):
        if obs.state not in VALID_STATES:
            continue
        t_i = obs.observed_at
        if i + 1 < len(clipped):
            t_next = clipped[i + 1].observed_at
        else:
            t_next = end
        # Cover forward at most t_support, and not past the next sample / end.
        cover_end = min(t_i.timestamp() + t_support, t_next.timestamp(), end.timestamp())
        cover = max(0.0, cover_end - t_i.timestamp())
        _add(obs.state, cover)

    observed = focused + distracted
    # Numerical safety: never attribute more than duration
    if observed > duration:
        scale = duration / observed
        focused *= scale
        distracted *= scale
        observed = focused + distracted

    unknown = max(0.0, duration - observed)
    coverage_pct = (100.0 * observed / duration) if duration > 0 else 0.0
    if observed > 0:
        focus_pct: Optional[float] = 100.0 * focused / observed
    else:
        focus_pct = None

    return CoverageResult(
        observed_focused_seconds=focused,
        observed_distracted_seconds=distracted,
        unknown_seconds=unknown,
        monitoring_coverage_pct=coverage_pct,
        focus_percentage=focus_pct,
        session_duration_seconds=duration,
    )


def episode_close_on_unknown(
    open_started_at: datetime,
    unknown_at: datetime,
) -> datetime:
    """Close an open distraction episode at the UNKNOWN observation time."""
    return _as_utc_naive(unknown_at)


def empty_coverage(duration_seconds: float = 0.0) -> CoverageResult:
    return CoverageResult(
        observed_focused_seconds=0.0,
        observed_distracted_seconds=0.0,
        unknown_seconds=max(0.0, duration_seconds),
        monitoring_coverage_pct=0.0,
        focus_percentage=None,
        session_duration_seconds=max(0.0, duration_seconds),
    )
