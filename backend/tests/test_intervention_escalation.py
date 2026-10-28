"""
Escalation fix: Tier 1 ambient_cue does not take the pending lock or start
the cooldown, and fires at most once per distraction episode. Tiers 2–4 keep
the previous pending + cooldown behaviour.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.intervention_engine import (
    InterventionEngine,
    TYPE_AMBIENT,
    TYPE_PACING,
    TYPE_MILESTONE,
)

BASE_NOW = 1_700_000_000.0
WALL0 = datetime(2026, 1, 1, 0, 0, 0)


class Episode:
    """Same duration formula as DistractionEvent.duration_seconds."""

    def __init__(self, started_at: datetime, eid: int | None = 1):
        self.id = eid
        self.started_at = started_at
        self.ended_at = None

    def duration_seconds(self, now=None) -> float:
        end = self.ended_at or now or datetime.utcnow()
        if not self.started_at:
            return 0.0
        return max(0.0, (end - self.started_at).total_seconds())


def _simulate(response: str | None, seconds: int = 120) -> list[dict]:
    engine = InterventionEngine(cooldown_seconds=30.0, enabled_tiers=None)
    episode = Episode(WALL0)
    fires = []
    for t in range(0, seconds + 1, 2):
        if response is not None and fires:
            last = fires[-1]
            if (
                t == last["second"] + 2
                and engine._pending_intervention
                and last["tier"] >= 2
            ):
                engine.record_outcome(response)
        triggered = engine.decide_intervention(
            distraction_event=episode,
            is_distracted=True,
            is_quiz_context=False,
            now=BASE_NOW + t,
            wall_now=WALL0 + timedelta(seconds=t),
            observation_state="DISTRACTED",
        )
        if triggered is not None:
            fires.append(
                {
                    "second": t,
                    "tier": int(triggered.tier),
                    "intervention_type": triggered.intervention_type,
                }
            )
    return fires


def test_default_continuous_distracted_reaches_tier2():
    fires = _simulate(None, 120)
    assert fires, "expected at least one intervention"
    assert fires[0]["tier"] == 1
    assert fires[0]["intervention_type"] == TYPE_AMBIENT
    assert any(f["tier"] == 2 and f["intervention_type"] == TYPE_PACING for f in fires)
    # Exact sequence for the report / regression
    assert fires == [
        {"second": 6, "tier": 1, "intervention_type": TYPE_AMBIENT},
        {"second": 10, "tier": 2, "intervention_type": TYPE_PACING},
    ]


def test_ignored_response_after_tier2_plus():
    fires = _simulate("ignored", 120)
    assert fires[0]["tier"] == 1
    assert any(f["tier"] == 2 for f in fires)
    # After ignored Tier 2, escalation should climb
    tiers = [f["tier"] for f in fires]
    assert 3 in tiers or 4 in tiers


def test_reengaged_response_after_tier2_plus():
    fires = _simulate("reengaged", 120)
    assert fires[0]["tier"] == 1
    assert any(f["tier"] == 2 for f in fires)
    # reengaged clears last_tier; later fires stay at duration-based tier
    assert all(f["tier"] <= 4 for f in fires)


def test_only_one_ambient_cue_per_episode():
    engine = InterventionEngine(cooldown_seconds=0.0)
    ep = Episode(WALL0, eid=7)
    first = engine.decide_intervention(
        distraction_event=ep,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 6,
        wall_now=WALL0 + timedelta(seconds=6),
    )
    assert first is not None and first.tier == 1
    assert engine._pending_intervention is False
    assert engine.last_intervention_at == 0.0
    second = engine.decide_intervention(
        distraction_event=ep,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 8,
        wall_now=WALL0 + timedelta(seconds=8),
    )
    assert second is None
    # New episode id allows another ambient
    ep2 = Episode(WALL0 + timedelta(seconds=20), eid=8)
    third = engine.decide_intervention(
        distraction_event=ep2,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 26,
        wall_now=WALL0 + timedelta(seconds=26),
    )
    # duration of ep2 at wall+26 is 6 s → tier 1 again
    assert third is not None and third.tier == 1


def test_enabled_tiers_3_4_at_6s_fires_nothing():
    engine = InterventionEngine(cooldown_seconds=30.0, enabled_tiers=[3, 4])
    episode = Episode(WALL0)
    triggered = engine.decide_intervention(
        distraction_event=episode,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 6,
        wall_now=WALL0 + timedelta(seconds=6),
    )
    assert triggered is None
    assert engine._pending_intervention is False


def test_unknown_mid_episode_and_focused_reset():
    engine = InterventionEngine(cooldown_seconds=0.0)
    ep = Episode(WALL0, eid=3)
    amb = engine.decide_intervention(
        distraction_event=ep,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 6,
        wall_now=WALL0 + timedelta(seconds=6),
    )
    assert amb is not None and amb.tier == 1
    assert engine._ambient_episode_key is not None

    # UNKNOWN holds ambient key / does not reset
    assert (
        engine.decide_intervention(
            distraction_event=None,
            is_distracted=False,
            observation_state="UNKNOWN",
            now=BASE_NOW + 7,
        )
        is None
    )
    assert engine._ambient_episode_key is not None
    assert engine.last_tier == 1

    # FOCUSED clears ambient key so a later episode can cue again
    assert (
        engine.decide_intervention(
            distraction_event=None,
            is_distracted=False,
            observation_state="FOCUSED",
            now=BASE_NOW + 8,
        )
        is None
    )
    assert engine._ambient_episode_key is None
    assert engine.last_tier is None

    ep2 = Episode(WALL0 + timedelta(seconds=10), eid=4)
    again = engine.decide_intervention(
        distraction_event=ep2,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 16,
        wall_now=WALL0 + timedelta(seconds=16),
    )
    assert again is not None and again.tier == 1


def test_ambient_does_not_block_tier2_inside_band():
    """Regression for REPORT.md §9: Tier 2 must appear inside the 10–20 s band."""
    engine = InterventionEngine(cooldown_seconds=30.0)
    ep = Episode(WALL0, eid=9)
    t1 = engine.decide_intervention(
        distraction_event=ep,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 6,
        wall_now=WALL0 + timedelta(seconds=6),
    )
    assert t1 is not None and t1.tier == 1
    assert engine._pending_intervention is False
    t2 = engine.decide_intervention(
        distraction_event=ep,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 12,
        wall_now=WALL0 + timedelta(seconds=12),
    )
    assert t2 is not None
    assert t2.tier == 2
    assert t2.intervention_type == TYPE_PACING
    assert engine._pending_intervention is True
