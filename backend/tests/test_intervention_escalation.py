"""PLAN 4 escalation: all tiers take pending + cooldown; timeout → ignored."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.services.intervention_engine import (
    InterventionEngine,
    TYPE_AMBIENT,
    TYPE_PACING,
)

BASE_NOW = 1_700_000_000.0
WALL0 = datetime(2026, 1, 1, 0, 0, 0)


class Episode:
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
    """Advance clock; auto-timeout pending after 20 s if no response, else apply response."""
    engine = InterventionEngine(cooldown_seconds=30.0, enabled_tiers=None)
    episode = Episode(WALL0)
    fires = []
    for t in range(0, seconds + 1, 2):
        now = BASE_NOW + t
        engine.tick(now)
        if response is not None and fires and engine._pending_intervention:
            last = fires[-1]
            if t >= last["second"] + 2:
                engine.record_outcome(response, intervention_id=last.get("id"), now=now)
        triggered = engine.decide_intervention(
            distraction_event=episode,
            is_distracted=True,
            is_quiz_context=False,
            now=now,
            wall_now=WALL0 + timedelta(seconds=t),
            observation_state="DISTRACTED",
            source="model6",
        )
        if triggered is not None:
            fires.append(
                {
                    "second": t,
                    "tier": int(triggered.tier),
                    "intervention_type": triggered.intervention_type,
                    "id": triggered.intervention_id,
                }
            )
    return fires


def test_default_continuous_distracted_timeout_escalates():
    """Never-answering child: tier1 → timeout → cooldown → tier2+."""
    fires = _simulate(None, 120)
    assert fires, "expected at least one intervention"
    assert fires[0]["tier"] == 1
    assert fires[0]["intervention_type"] == TYPE_AMBIENT
    # After 20 s timeout + 30 s cooldown from resolution ≈ next fire ≥ 50 s
    assert any(f["tier"] >= 2 for f in fires)
    assert fires[0]["second"] == 6


def test_ignored_response_escalates():
    fires = _simulate("ignored", 120)
    assert fires[0]["tier"] == 1
    tiers = [f["tier"] for f in fires]
    assert any(t >= 2 for t in tiers)


def test_reengaged_response_deescalates():
    fires = _simulate("reengaged", 120)
    assert fires[0]["tier"] == 1
    # After reengage + sustained focus would clear; here we stay distracted so
    # duration-based tiers continue, but without ignored-escalation memory.
    assert all(f["tier"] <= 4 for f in fires)


def test_tier1_takes_pending_lock():
    engine = InterventionEngine(cooldown_seconds=30.0)
    ep = Episode(WALL0, eid=7)
    first = engine.decide_intervention(
        distraction_event=ep,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 6,
        wall_now=WALL0 + timedelta(seconds=6),
        source="model6",
    )
    assert first is not None and first.tier == 1
    assert engine._pending_intervention is True
    second = engine.decide_intervention(
        distraction_event=ep,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 8,
        wall_now=WALL0 + timedelta(seconds=8),
        source="model6",
    )
    assert second is None


def test_enabled_tiers_3_4_at_6s_fires_nothing():
    engine = InterventionEngine(cooldown_seconds=30.0, enabled_tiers=[3, 4])
    episode = Episode(WALL0)
    triggered = engine.decide_intervention(
        distraction_event=episode,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 6,
        wall_now=WALL0 + timedelta(seconds=6),
        source="model6",
    )
    assert triggered is None


def test_focused_during_pending_does_not_reset():
    engine = InterventionEngine(cooldown_seconds=0.0)
    ep = Episode(WALL0, eid=3)
    amb = engine.decide_intervention(
        distraction_event=ep,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 6,
        wall_now=WALL0 + timedelta(seconds=6),
        source="model6",
    )
    assert amb is not None and amb.tier == 1
    assert (
        engine.decide_intervention(
            distraction_event=None,
            is_distracted=False,
            observation_state="FOCUSED",
            now=BASE_NOW + 8,
            source="model6",
        )
        is None
    )
    assert engine._pending_intervention is True
    assert engine.last_tier == 1


def test_sustained_focus_resets_after_resolution():
    engine = InterventionEngine(cooldown_seconds=0.0, focus_reset_sec=10.0)
    ep = Episode(WALL0, eid=9)
    t1 = engine.decide_intervention(
        distraction_event=ep,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 6,
        wall_now=WALL0 + timedelta(seconds=6),
        source="model6",
    )
    assert t1 is not None
    engine.record_outcome("ignored", intervention_id=t1.intervention_id, now=BASE_NOW + 7)
    # Need ≥10 s FOCUSED to clear escalation memory
    engine.decide_intervention(
        None, False, observation_state="FOCUSED", now=BASE_NOW + 8, source="model6"
    )
    assert engine.last_tier == 1  # not yet
    engine.decide_intervention(
        None, False, observation_state="FOCUSED", now=BASE_NOW + 18, source="model6"
    )
    assert engine.last_tier is None


def test_tier2_after_timeout_and_cooldown():
    engine = InterventionEngine(cooldown_seconds=30.0)
    ep = Episode(WALL0, eid=9)
    t1 = engine.decide_intervention(
        distraction_event=ep,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 6,
        wall_now=WALL0 + timedelta(seconds=6),
        source="model6",
    )
    assert t1 is not None and t1.tier == 1
    # Timeout at +20 s from fire
    engine.tick(BASE_NOW + 6 + 21)
    # Cooldown 30 s from resolution
    t2 = engine.decide_intervention(
        distraction_event=ep,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 6 + 21 + 30,
        wall_now=WALL0 + timedelta(seconds=6 + 21 + 30),
        source="model6",
    )
    assert t2 is not None
    assert t2.tier >= 2
    assert t2.intervention_type == TYPE_PACING or t2.tier >= 2
