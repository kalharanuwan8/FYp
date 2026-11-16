"""PLAN 4 intervention scenario tests."""

from __future__ import annotations

import threading
import time

from app.services.intervention_engine import (
    InterventionEngine,
    TYPE_AMBIENT,
    TYPE_NOISE_NOTICE,
    TYPE_SUGGEST_BREAK,
    clear_session_engine,
    get_session_engine,
)


class _Ep:
    def __init__(self, duration):
        self._d = duration
        self.id = 1
        self.started_at = None

    def duration_seconds(self, now=None):
        return self._d


def test_timeout_becomes_ignored_then_escalates():
    clock = {"t": 100.0}
    eng = InterventionEngine(now_fn=lambda: clock["t"], cooldown_seconds=20.0)
    # Tier 1 at 5 s look-away
    t1 = eng.decide_intervention(_Ep(6), True, observation_state="DISTRACTED", source="model6")
    assert t1 is not None and t1.tier == 1
    assert t1.deadline == clock["t"] + 6.0  # PLAN 5: T1 = 6 s
    # Expire
    clock["t"] += 7.0
    rec = eng.tick()
    assert rec["outcome"] == "ignored"
    assert rec["user_response"] == "timeout"
    # PLAN 5: T1 ignore → force T2 immediately (no cooldown)
    t2 = eng.force_intervention(2, source="escalation", bypass=True, now=clock["t"])
    assert t2 is not None and t2.tier == 2
    assert t2.deadline == clock["t"] + 20.0


def test_t1_timeout_forces_t2_immediately():
    clock = {"t": 0.0}
    eng = InterventionEngine(now_fn=lambda: clock["t"], cooldown_seconds=20.0)
    t1 = eng.decide_intervention(_Ep(6), True, observation_state="DISTRACTED", source="model6")
    assert t1 is not None and t1.tier == 1
    clock["t"] = 6.0
    rec = eng.tick()
    assert rec is not None and rec["tier"] == 1
    t2 = eng.force_intervention(2, source="escalation", bypass=True)
    assert t2 is not None and t2.tier == 2
    assert t2.source == "escalation"


def test_stale_or_mismatched_id_rejected():
    eng = InterventionEngine(now_fn=lambda: 0.0)
    t = eng.decide_intervention(_Ep(6), True, observation_state="DISTRACTED", source="model6")
    assert t is not None
    assert eng.record_outcome("ignored", intervention_id="wrong_id") is False
    assert eng.record_outcome("ignored", intervention_id=t.intervention_id) is True


def test_noise_outcome_isolation():
    clock = {"t": 0.0}
    eng = InterventionEngine(now_fn=lambda: clock["t"], cooldown_seconds=20.0)
    n = eng.consider_noise(noise_dbfs=-20.0)
    assert n is not None and n.intervention_type == TYPE_NOISE_NOTICE
    eng.record_outcome("ignored", intervention_id=n.intervention_id)
    assert eng.last_tier is None  # noise must not set visual last_tier
    assert eng.last_outcome is None
    clock["t"] += 21.0
    t = eng.decide_intervention(_Ep(6), True, observation_state="DISTRACTED", source="model6")
    assert t is not None and t.tier == 1  # not escalated from noise ignore


def test_focused_blip_during_pending_does_not_reset():
    eng = InterventionEngine(now_fn=lambda: 0.0)
    t = eng.decide_intervention(_Ep(6), True, observation_state="DISTRACTED", source="model6")
    assert t is not None
    # FOCUSED while pending — must not clear last_tier / pending
    assert (
        eng.decide_intervention(None, False, observation_state="FOCUSED", source="model6")
        is None
    )
    assert eng._pending is not None
    assert eng.last_tier == 1


def test_unknown_mid_episode_no_repeated_cue():
    clock = {"t": 0.0}
    eng = InterventionEngine(now_fn=lambda: clock["t"], cooldown_seconds=20.0)
    t1 = eng.decide_intervention(_Ep(6), True, observation_state="DISTRACTED", source="model6")
    assert t1 is not None
    eng.record_outcome("ignored", intervention_id=t1.intervention_id)
    clock["t"] += 21.0
    # UNKNOWN must not fire
    assert (
        eng.decide_intervention(_Ep(20), True, observation_state="UNKNOWN", source="model6")
        is None
    )


def test_break_no_immediate_repeat():
    clock = {"t": 0.0}
    eng = InterventionEngine(now_fn=lambda: clock["t"], cooldown_seconds=20.0)
    # Force tier 4 twice: second should wait for cooldown after resolution
    t4a = eng.force_intervention(4, source="model6")
    assert t4a is not None
    # Breaks are timeout-exempt — resolve manually
    eng.record_outcome("ended", intervention_id=t4a.intervention_id)
    # Immediate re-fire blocked by cooldown
    assert eng.force_intervention(4, source="model6") is None
    clock["t"] += 21.0
    t4b = eng.force_intervention(4, source="model6")
    assert t4b is not None
    assert t4b.intervention_type == TYPE_SUGGEST_BREAK  # t4_used


def test_demo_force_bypass_pending_and_cooldown():
    clock = {"t": 0.0}
    eng = InterventionEngine(now_fn=lambda: clock["t"], cooldown_seconds=20.0)
    t1 = eng.decide_intervention(_Ep(6), True, observation_state="DISTRACTED", source="model6")
    assert t1 is not None and eng._pending is not None
    # Without bypass: blocked by pending
    assert eng.force_intervention(3, source="manual") is None
    # With bypass: clears pending and fires immediately
    t3 = eng.force_intervention(3, source="demo", bypass=True)
    assert t3 is not None and t3.tier == 3 and t3.source == "demo"


def test_rule_source_capped_at_tier_2():
    clock = {"t": 0.0}
    eng = InterventionEngine(now_fn=lambda: clock["t"])
    # Long duration would be tier 4, but rule caps at 2
    t = eng.decide_intervention(_Ep(50), True, observation_state="DISTRACTED", source="rule")
    assert t is not None and t.tier <= 2


def test_coverage_gate_blocks_prompts():
    eng = InterventionEngine(now_fn=lambda: 0.0)
    assert (
        eng.decide_intervention(
            _Ep(20),
            True,
            observation_state="DISTRACTED",
            source="model6",
            coverage_ratio_30s=0.2,
        )
        is None
    )


def test_get_session_engine_threadsafe_smoke():
    clear_session_engine("s-smoke")
    errors = []

    def worker():
        try:
            for _ in range(50):
                eng = get_session_engine("s-smoke", cooldown_seconds=20.0)
                eng.tick()
                eng.decide_intervention(
                    _Ep(6), True, observation_state="DISTRACTED", source="model6"
                )
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert not errors
    clear_session_engine("s-smoke")
