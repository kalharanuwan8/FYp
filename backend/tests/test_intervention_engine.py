from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.intervention_engine import (
    InterventionEngine,
    distraction_level_from_duration,
    TYPE_AMBIENT,
    TYPE_PACING,
    TYPE_MILESTONE,
    TYPE_HINT,
    TYPE_PACING_REDUCTION,
    TYPE_SUGGEST_BREAK,
)


def _episode(age_seconds: float):
    return SimpleNamespace(
        started_at=datetime.utcnow() - timedelta(seconds=age_seconds),
        ended_at=None,
        duration_seconds=lambda now=None, age=age_seconds: age,
    )


def test_distraction_level_bands():
    assert distraction_level_from_duration(3) == 0
    assert distraction_level_from_duration(5) == 1
    assert distraction_level_from_duration(12) == 2
    assert distraction_level_from_duration(25) == 3
    assert distraction_level_from_duration(45) == 4


def test_tier1_ambient_after_mild_duration():
    engine = InterventionEngine(cooldown_seconds=0.0)
    res = engine.decide_intervention(
        distraction_event=_episode(7),
        is_distracted=True,
        is_quiz_context=False,
        now=100.0,
    )
    assert res is not None
    assert res.tier == 1
    assert res.intervention_type == TYPE_AMBIENT


def test_cooldown_suppresses_repeat():
    engine = InterventionEngine(cooldown_seconds=60.0)
    res1 = engine.decide_intervention(
        distraction_event=_episode(8), is_distracted=True, now=100.0
    )
    assert res1 is not None
    # Pending without outcome — blocked
    assert engine.decide_intervention(
        distraction_event=_episode(8), is_distracted=True, now=130.0
    ) is None
    engine.record_outcome("reengaged")
    # Still in cooldown window
    assert engine.decide_intervention(
        distraction_event=_episode(8), is_distracted=True, now=130.0
    ) is None
    # After cooldown
    res2 = engine.decide_intervention(
        distraction_event=_episode(8), is_distracted=True, now=165.0
    )
    assert res2 is not None
    assert res2.tier == 1


def test_ignored_escalates_one_tier():
    engine = InterventionEngine(cooldown_seconds=0.0)
    res1 = engine.decide_intervention(
        distraction_event=_episode(8), is_distracted=True, now=100.0
    )
    assert res1.tier == 1
    engine.record_outcome("ignored")
    res2 = engine.decide_intervention(
        distraction_event=_episode(8), is_distracted=True, now=101.0
    )
    assert res2 is not None
    assert res2.tier == 2
    assert res2.intervention_type == TYPE_PACING


def test_quiz_context_uses_hint_injection():
    engine = InterventionEngine(cooldown_seconds=0.0)
    res = engine.decide_intervention(
        distraction_event=_episode(25),
        is_distracted=True,
        is_quiz_context=True,
        now=100.0,
    )
    assert res.tier == 3
    assert res.intervention_type == TYPE_HINT
    assert "hint_text" in res.payload


def test_content_context_uses_milestone_quiz():
    engine = InterventionEngine(cooldown_seconds=0.0)
    res = engine.decide_intervention(
        distraction_event=_episode(25),
        is_distracted=True,
        is_quiz_context=False,
        now=100.0,
    )
    assert res.intervention_type == TYPE_MILESTONE


def test_tier4_pacing_then_suggest_break():
    engine = InterventionEngine(cooldown_seconds=0.0)
    res1 = engine.decide_intervention(
        distraction_event=_episode(50), is_distracted=True, now=100.0
    )
    assert res1.intervention_type == TYPE_PACING_REDUCTION
    engine.record_outcome("ignored")
    res2 = engine.decide_intervention(
        distraction_event=_episode(50), is_distracted=True, now=101.0
    )
    assert res2.intervention_type == TYPE_SUGGEST_BREAK


def test_disabled_tier_falls_back():
    engine = InterventionEngine(cooldown_seconds=0.0, enabled_tiers=[1, 2])
    res = engine.decide_intervention(
        distraction_event=_episode(50), is_distracted=True, now=100.0
    )
    # Level 4 requested but only 1–2 enabled → fall back to 2
    assert res.tier == 2
    assert res.intervention_type == TYPE_PACING


def test_all_tiers_disabled_fires_nothing():
    """Regression: explicit empty enabled_tiers must not coerce to [1,2,3,4]."""
    engine = InterventionEngine(cooldown_seconds=0.0, enabled_tiers=[])
    assert engine.enabled_tiers == set()
    res = engine.decide_intervention(
        distraction_event=_episode(50), is_distracted=True, now=100.0
    )
    assert res is None


def test_get_enabled_tiers_preserves_empty_config(app):
    """Route helper must return [] when every subject tier flag is off."""
    from app.db_models import GradeLevel, Subject, InterventionConfig
    from app.extensions import db
    from app.routes.session import _get_enabled_tiers

    with app.app_context():
        gl = GradeLevel(name="G-tiers-off")
        db.session.add(gl)
        db.session.flush()
        subject = Subject(title="No Tiers Subject", grade_level_id=gl.id)
        db.session.add(subject)
        db.session.flush()
        cfg = InterventionConfig(
            subject_id=subject.id,
            tier1_enabled=False,
            tier2_enabled=False,
            tier3_enabled=False,
            tier4_enabled=False,
        )
        db.session.add(cfg)
        db.session.commit()
        assert _get_enabled_tiers(subject.id) == []


def test_focus_resets_escalation():
    engine = InterventionEngine(cooldown_seconds=0.0)
    engine.decide_intervention(
        distraction_event=_episode(8),
        is_distracted=True,
        observation_state="DISTRACTED",
        now=100.0,
    )
    engine.record_outcome("ignored")
    assert engine.decide_intervention(
        distraction_event=None,
        is_distracted=False,
        observation_state="FOCUSED",
        now=101.0,
    ) is None
    assert engine.last_tier is None


def test_unknown_holds_without_focus_reset():
    engine = InterventionEngine(cooldown_seconds=0.0)
    engine.decide_intervention(
        distraction_event=_episode(8),
        is_distracted=True,
        observation_state="DISTRACTED",
        now=100.0,
    )
    assert engine._pending_intervention is True
    assert (
        engine.decide_intervention(
            distraction_event=None,
            is_distracted=False,
            observation_state="UNKNOWN",
            now=101.0,
        )
        is None
    )
    assert engine._pending_intervention is True
    assert engine.last_tier is not None
