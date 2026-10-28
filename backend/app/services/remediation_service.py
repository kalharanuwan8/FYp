"""
Adaptive content re-delivery after a failed quiz on a video module.

Thresholds (error rate, coverage, focus) are engineering parameters read from
Flask config — not clinical thresholds.
"""

from __future__ import annotations

from typing import Any, Optional

from flask import current_app

from app.db_models.course import ModuleContent, ModuleMilestoneItem
from app.db_models.quiz import Quiz
from app.db_models.remediation import RemediationEvent
from app.db_models.session import LearningSession
from app.extensions import db
from app.services.observation_coverage import FOCUS_METRIC_VERSION

REASON_COMPREHENSION = "comprehension_likely"
REASON_ATTENTION = "attention_likely"
REASON_INSUFFICIENT = "insufficient_monitoring"

PATH_DIFFERENT = "different_format"
PATH_GUIDED = "guided_rewatch"

KIND_ALTERNATIVE = "alternative_material"
KIND_PACK = "approved_pack"
KIND_GUIDED = "guided_rewatch"

VALID_CHOICES = frozenset({KIND_ALTERNATIVE, KIND_PACK, KIND_GUIDED})


def compute_error_rate(correct_count: int, total_questions: int) -> float:
    if total_questions <= 0:
        return 0.0
    wrong = total_questions - correct_count
    return wrong / float(total_questions)


def should_trigger_remediation(
    error_rate: float, has_video: bool, threshold: Optional[float] = None
) -> bool:
    """Trigger only when error_rate is strictly greater than the threshold."""
    if not has_video:
        return False
    if threshold is None:
        threshold = float(
            current_app.config.get("REMEDIATION_ERROR_RATE_THRESHOLD", 0.50)
        )
    return error_rate > threshold


def decide_reason(
    coverage_pct: Optional[float],
    focus_pct: Optional[float],
    coverage_min: Optional[float] = None,
    focus_min: Optional[float] = None,
) -> str:
    """
    Map stored observed_v1 coverage/focus to a reason label.

    Engineering parameters (not clinical thresholds): coverage_min, focus_min.
    """
    if coverage_min is None:
        coverage_min = float(
            current_app.config.get("REMEDIATION_COVERAGE_MIN_PCT", 50.0)
        )
    if focus_min is None:
        focus_min = float(current_app.config.get("REMEDIATION_FOCUS_MIN_PCT", 70.0))

    if coverage_pct is None or coverage_pct < coverage_min:
        return REASON_INSUFFICIENT
    if focus_pct is None:
        return REASON_INSUFFICIENT
    if focus_pct >= focus_min:
        return REASON_COMPREHENSION
    return REASON_ATTENTION


def _milestone_offer_dicts(items: list[ModuleMilestoneItem]) -> list[dict]:
    """Student-facing milestone list — omit correct_option."""
    out = []
    for m in items:
        if not m.is_active:
            continue
        out.append(
            {
                "id": m.id,
                "question": m.question,
                "options": m.options_json or [],
                "hint_text": m.hint_text,
                "sequence_order": m.sequence_order,
            }
        )
    return out


def _find_alternative_material(contents: list[ModuleContent]) -> Optional[ModuleContent]:
    for c in contents:
        if c.content_type in ("document", "other"):
            return c
    return None


def _find_approved_pack(
    contents: list[ModuleContent], prefer_video: bool = True
) -> Optional[tuple[ModuleContent, list[ModuleMilestoneItem]]]:
    """
    Teacher-saved LLM pack: non-empty summary plus at least one active milestone.
    Prefer the video row when prefer_video is True.
    """
    ordered = list(contents)
    if prefer_video:
        ordered = sorted(
            contents, key=lambda c: (0 if c.content_type == "video" else 1, c.id)
        )
    for c in ordered:
        summary = (c.summary or "").strip()
        if not summary:
            continue
        active = [m for m in (c.milestone_items or []) if m.is_active]
        if not active:
            continue
        return c, sorted(active, key=lambda m: m.sequence_order)
    return None


def _find_video(contents: list[ModuleContent]) -> Optional[ModuleContent]:
    for c in contents:
        if c.content_type == "video":
            return c
    return None


def build_offers(
    reason: str, contents: list[ModuleContent]
) -> tuple[str, list[dict[str, Any]]]:
    """
    Build student offers and the stored path.

    Content priority for the different-format path: (a) document/other,
    (b) approved pack, (c) guided re-watch.
    attention_likely always includes guided re-watch and may also include (a)/(b).
    """
    alt = _find_alternative_material(contents)
    pack = _find_approved_pack(contents)
    video = _find_video(contents)

    def offer_alternative(c: ModuleContent) -> dict:
        return {
            "kind": KIND_ALTERNATIVE,
            "content_id": c.id,
            "content_type": c.content_type,
            "title": c.title,
            "file_url": c.file_url,
        }

    def offer_pack(c: ModuleContent, milestones: list[ModuleMilestoneItem]) -> dict:
        return {
            "kind": KIND_PACK,
            "content_id": c.id,
            "content_type": c.content_type,
            "title": c.title,
            "file_url": c.file_url,
            "summary": c.summary,
            "milestones": _milestone_offer_dicts(milestones),
        }

    def offer_guided(c: ModuleContent) -> dict:
        active = [m for m in (c.milestone_items or []) if m.is_active]
        active = sorted(active, key=lambda m: m.sequence_order)
        return {
            "kind": KIND_GUIDED,
            "content_id": c.id,
            "content_type": c.content_type,
            "title": c.title,
            "file_url": c.file_url,
            "milestones": _milestone_offer_dicts(active),
        }

    if reason == REASON_ATTENTION:
        offers: list[dict] = []
        if video:
            offers.append(offer_guided(video))
        if alt:
            offers.append(offer_alternative(alt))
        elif pack:
            offers.append(offer_pack(pack[0], pack[1]))
        path = PATH_GUIDED
        if not offers and video:
            offers = [offer_guided(video)]
        return path, offers

    # comprehension_likely / insufficient_monitoring → different format first
    if alt:
        return PATH_DIFFERENT, [offer_alternative(alt)]
    if pack:
        return PATH_DIFFERENT, [offer_pack(pack[0], pack[1])]
    if video:
        return PATH_GUIDED, [offer_guided(video)]
    return PATH_GUIDED, []


def latest_observed_session(
    student_id: int, module_id: int
) -> Optional[LearningSession]:
    """
    Newest sealed monitored session for this student/module that already has
    an observed_v1 snapshot. Does not recompute from heartbeat rows.
    """
    return (
        LearningSession.query.filter_by(
            student_id=student_id,
            module_id=module_id,
            is_monitored=True,
            focus_metric_version=FOCUS_METRIC_VERSION,
        )
        .filter(LearningSession.end_time.isnot(None))
        .order_by(LearningSession.end_time.desc())
        .first()
    )


def module_has_video(module_id: int) -> bool:
    return (
        ModuleContent.query.filter_by(module_id=module_id, content_type="video").first()
        is not None
    )


def build_remediation_for_attempt(
    *,
    student_id: int,
    quiz: Quiz,
    attempt_id: int,
    correct_count: int,
    total_questions: int,
) -> Optional[dict[str, Any]]:
    """
    Decide remediation, persist RemediationEvent, return student payload.
    Returns None when remediation should not trigger.
    """
    error_rate = compute_error_rate(correct_count, total_questions)
    has_video = module_has_video(quiz.module_id)
    if not should_trigger_remediation(error_rate, has_video):
        return None

    session = latest_observed_session(student_id, quiz.module_id)
    coverage = session.monitoring_coverage_pct if session else None
    focus = session.focus_percentage if session else None
    reason = decide_reason(coverage, focus)

    contents = ModuleContent.query.filter_by(module_id=quiz.module_id).all()
    path, offers = build_offers(reason, contents)

    event = RemediationEvent(
        student_id=student_id,
        module_id=quiz.module_id,
        quiz_attempt_id=attempt_id,
        session_id=session.id if session else None,
        error_rate=round(error_rate, 4),
        focus_percentage=focus,
        monitoring_coverage_pct=coverage,
        path=path,
        reason=reason,
        content_shown={"offers": offers},
    )
    db.session.add(event)
    db.session.commit()

    return {
        "event_id": event.id,
        "error_rate": event.error_rate,
        "path": path,
        "reason": reason,
        "focus_percentage": focus,
        "monitoring_coverage_pct": coverage,
        "offers": offers,
    }
