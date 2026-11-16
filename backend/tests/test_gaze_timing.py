"""PLAN 8: T1 timing from INTERVENTION_T1_SEC + gaze episode backdating."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.intervention_engine import (
    InterventionEngine,
    distraction_level_from_duration,
)


class _Ep:
    def __init__(self, duration, started_at=None):
        self._d = duration
        self.started_at = started_at
        self.id = 1

    def duration_seconds(self, now=None):
        return self._d


def test_t1_fires_at_three_seconds_with_backdated_episode():
    """Gaze dwell 2 s + backdate → episode age ≥3 s → T1 on next decide."""
    eng = InterventionEngine(cooldown_seconds=0.0, now_fn=lambda: 100.0)
    # Eyes left 2 s ago; heartbeat just entered DISTRACTED → backdated duration 3+
    ep = _Ep(3.0)
    t1 = eng.decide_intervention(
        ep, True, observation_state="DISTRACTED", source="gaze_screen", now=100.0
    )
    assert t1 is not None and t1.tier == 1


def test_t1_setting_six_delays_prompt(monkeypatch):
    monkeypatch.setenv("INTERVENTION_T1_SEC", "6.0")
    # With T1=6, a 5 s episode is still level 0; at 6 s T1 fires.
    assert distraction_level_from_duration(5.0, t1_sec=6.0) == 0
    assert distraction_level_from_duration(6.0, t1_sec=6.0) == 1
    assert distraction_level_from_duration(12.0, t1_sec=6.0) == 2
    assert distraction_level_from_duration(25.0, t1_sec=6.0) == 3
    eng = InterventionEngine(cooldown_seconds=0.0, now_fn=lambda: 0.0)
    assert (
        eng.decide_intervention(
            _Ep(5.0), True, observation_state="DISTRACTED", source="model6", now=0.0
        )
        is None
    )
    t1 = eng.decide_intervention(
        _Ep(6.0), True, observation_state="DISTRACTED", source="model6", now=0.0
    )
    assert t1 is not None and t1.tier == 1


def test_t2_t3_bands_unchanged():
    assert distraction_level_from_duration(9.9, t1_sec=3.0) == 1
    assert distraction_level_from_duration(10.0, t1_sec=3.0) == 2
    assert distraction_level_from_duration(19.9, t1_sec=3.0) == 2
    assert distraction_level_from_duration(20.0, t1_sec=3.0) == 3
    assert distraction_level_from_duration(40.0, t1_sec=3.0) == 4
