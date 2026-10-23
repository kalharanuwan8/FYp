from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.session_schema import HeartbeatSchema, InterventionResponseSchema
from app.services.intervention_engine import (
    InterventionEngine,
    TYPE_NOISE_NOTICE,
)
from app.services.noise_monitor import NoiseMonitor


def _calibrate(monitor, level=-50.0):
    return [monitor.update(level) for _ in range(5)]


def _episode(age_seconds: float):
    return SimpleNamespace(
        started_at=datetime.utcnow() - timedelta(seconds=age_seconds),
        ended_at=None,
        duration_seconds=lambda now=None, age=age_seconds: age,
    )


def test_baseline_is_median_of_first_five_samples():
    monitor = NoiseMonitor()
    for level in (-40.0, -60.0, -50.0, -55.0):
        assert monitor.update(level) is False
        assert monitor.is_calibrated is False
    assert monitor.update(-45.0) is False
    assert monitor.is_calibrated is True
    assert monitor.baseline_dbfs == -50.0


def test_single_spike_does_not_fire_and_quiet_sample_resets_streak():
    monitor = NoiseMonitor()
    _calibrate(monitor)
    assert monitor.update(-20.0) is False
    assert monitor.update(-20.0) is False
    assert monitor.update(-20.0) is False
    # Quiet sample breaks the run — a fresh sustained run is needed.
    assert monitor.update(-50.0) is False
    assert monitor.update(-20.0) is False
    assert monitor.update(-20.0) is False
    assert monitor.update(-20.0) is False


def test_four_sustained_loud_beats_fire():
    monitor = NoiseMonitor()
    _calibrate(monitor)
    assert monitor.update(-30.0) is False  # +20 dB over baseline
    assert monitor.update(-30.0) is False
    assert monitor.update(-30.0) is False
    assert monitor.update(-30.0) is True


def test_unmarked_detection_stays_pending_so_it_is_not_lost():
    # If the caller could not show the notice (e.g. a visual intervention
    # was pending), the next usable sample reports the detection again.
    monitor = NoiseMonitor()
    _calibrate(monitor)
    for _ in range(4):
        monitor.update(-30.0)
    assert monitor.update(-50.0) is True  # even a quiet sample surfaces it
    assert monitor.notice_shown is False


def test_notice_never_fires_again_after_being_shown():
    monitor = NoiseMonitor()
    _calibrate(monitor)
    for _ in range(3):
        assert monitor.update(-30.0) is False
    assert monitor.update(-30.0) is True
    monitor.mark_notice_shown()
    assert monitor.notice_shown is True
    # Continued or renewed loud noise later in the session: nothing.
    for _ in range(6):
        assert monitor.update(-30.0) is False
    assert monitor.update(-10.0) is False


def test_lesson_audio_samples_are_ignored():
    monitor = NoiseMonitor()
    for _ in range(5):
        assert monitor.update(-10.0, lesson_audio_active=True) is False
    assert monitor.is_calibrated is False

    _calibrate(monitor)
    for _ in range(4):
        assert monitor.update(-10.0, lesson_audio_active=True) is False
    assert monitor.loud_streak == 0


def test_missing_mic_samples_are_ignored():
    monitor = NoiseMonitor()
    assert monitor.update(None) is False
    assert monitor.is_calibrated is False


def test_already_loud_room_fires_once_after_calibration():
    monitor = NoiseMonitor()
    results = [monitor.update(-15.0) for _ in range(5)]
    assert results == [False, False, False, False, True]
    # Shares the one-time latch: once shown, it never fires again.
    monitor.mark_notice_shown()
    assert monitor.update(-15.0) is False
    assert monitor.update(-5.0) is False


def test_consider_noise_fires_tier1_notice_without_touching_visual_state():
    engine = InterventionEngine(cooldown_seconds=30.0)
    res = engine.consider_noise(now=1000.0, noise_dbfs=-25.0, baseline_dbfs=-50.0)
    assert res is not None
    assert res.tier == 1
    assert res.intervention_type == TYPE_NOISE_NOTICE
    assert res.payload["trigger_source"] == "background_noise"
    # Visual escalation state untouched.
    assert engine.last_tier is None
    assert engine.last_outcome is None
    assert engine.t4_used is False


def test_consider_noise_blocked_by_pending_and_cooldown():
    engine = InterventionEngine(cooldown_seconds=30.0)
    assert engine.consider_noise(now=1000.0) is not None
    # One intervention already waiting for an outcome.
    assert engine.consider_noise(now=1010.0) is None
    engine.record_outcome("reengaged")
    # Cooldown still applies after the outcome.
    assert engine.consider_noise(now=1010.0) is None
    assert engine.consider_noise(now=1031.0) is not None


def test_ignored_noise_cue_does_not_escalate_next_visual_intervention():
    engine = InterventionEngine(cooldown_seconds=0.0)
    assert engine.consider_noise(now=100.0) is not None
    engine.record_outcome("ignored")
    res = engine.decide_intervention(
        distraction_event=_episode(8), is_distracted=True, now=101.0
    )
    assert res is not None
    assert res.tier == 1


def test_consider_noise_respects_disabled_tier1():
    engine = InterventionEngine(cooldown_seconds=0.0, enabled_tiers=[2, 3, 4])
    assert engine.consider_noise(now=100.0) is None


def test_heartbeat_schema_accepts_and_bounds_noise_fields():
    data = HeartbeatSchema(noise_dbfs=-42.5, lesson_audio_active=True)
    assert data.noise_dbfs == -42.5
    assert data.lesson_audio_active is True
    with pytest.raises(ValidationError):
        HeartbeatSchema(noise_dbfs=5.0)


def test_intervention_response_schema_validates_noise_action():
    data = InterventionResponseSchema(
        intervention_id=1, user_response="reengaged", noise_action="Headphones"
    )
    assert data.noise_action == "headphones"
    assert (
        InterventionResponseSchema(
            intervention_id=1, user_response="reengaged"
        ).noise_action
        is None
    )
    with pytest.raises(ValidationError):
        InterventionResponseSchema(
            intervention_id=1, user_response="reengaged", noise_action="ignore_it"
        )
