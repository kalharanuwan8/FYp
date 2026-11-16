"""PLAN 7: pause grace, honest episode clock, decision trace, heartbeat debug."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.db_models import DistractionEvent
from app.extensions import db
from app.services.intervention_engine import (
    PAUSE_GRACE_SEC,
    InterventionEngine,
)
from tests.test_session import _seed_student_session


class _Clock:
    """Episode whose wall age follows an injected engine clock."""

    def __init__(self, start_ts: float, ev_id: int = 1):
        self.start_ts = start_ts
        self.now_ts = start_ts
        self.id = ev_id
        self.started_at = None
        self.ended_at = None

    def duration_seconds(self, now=None):
        return self.now_ts - self.start_ts


def _step(engine, ep, ts, **kw):
    ep.now_ts = ts
    return engine.decide_intervention(
        distraction_event=ep, is_distracted=True, now=ts, source="model6", **kw
    )


def _run(engine, ep, t0, t1, step=2.0, **kw):
    fired = []
    t = t0
    while t <= t1 + 1e-9:
        r = _step(engine, ep, t, **kw)
        if r is not None:
            fired.append((t, r))
        t += step
    return fired


# ------------------------------------------------------------------ pause
def test_user_pause_grace_then_gentle_tier():
    eng = InterventionEngine(cooldown_seconds=0.0)
    ep = _Clock(0.0)
    fired = _run(eng, ep, 0.0, 30.0, content_state="paused", pause_reason="user")
    assert fired, "a paused + distracted student must eventually be nudged"
    t_first, first = fired[0]
    assert t_first >= PAUSE_GRACE_SEC
    assert first.tier <= 2


def test_pause_grace_reason_recorded():
    eng = InterventionEngine(cooldown_seconds=0.0)
    ep = _Clock(0.0)
    _step(eng, ep, 0.0, content_state="paused")
    _step(eng, ep, 2.0, content_state="paused")
    assert eng.last_decision["why"] == "paused_grace"
    assert eng.last_decision["pause_left_sec"] > 0


def test_paused_never_exceeds_tier2_even_after_long_episode():
    eng = InterventionEngine(cooldown_seconds=0.0)
    ep = _Clock(-60.0)  # already a long episode when the pause starts
    fired = _run(eng, ep, 0.0, 20.0, content_state="paused")
    assert fired and all(r.tier <= 2 for _, r in fired)


def test_ended_video_never_fires():
    eng = InterventionEngine(cooldown_seconds=0.0)
    ep = _Clock(0.0)
    assert _run(eng, ep, 0.0, 60.0, content_state="ended") == []
    assert eng.last_decision["why"] == "ended"


def test_intervention_pause_is_held():
    eng = InterventionEngine(cooldown_seconds=0.0)
    ep = _Clock(0.0)
    assert _run(eng, ep, 0.0, 30.0, content_state="paused", pause_reason="intervention") == []
    assert eng.last_decision["why"] == "paused_by_intervention"


def test_playing_fires_t1_at_five_seconds():
    eng = InterventionEngine(cooldown_seconds=0.0)
    ep = _Clock(0.0)
    fired = _run(eng, ep, 0.0, 8.0, content_state="playing")
    assert fired[0][0] == 6.0  # first heartbeat at/after 5 s
    assert fired[0][1].tier == 1


# ------------------------------------------------------- honest clock
def test_held_time_not_counted_first_fire_is_t1_after_resume():
    """Regression (session 158): ended/held for 30 s, then playing → T1, not T3."""
    eng = InterventionEngine(cooldown_seconds=0.0)
    ep = _Clock(0.0)
    assert _run(eng, ep, 0.0, 30.0, content_state="ended") == []
    fired = _run(eng, ep, 32.0, 50.0, content_state="playing")
    assert fired, "must fire once playing again"
    assert fired[0][1].tier == 1
    assert eng.last_decision["held_sec"] >= 28.0


def test_held_time_resets_on_new_episode():
    eng = InterventionEngine(cooldown_seconds=0.0)
    ep1 = _Clock(0.0, ev_id=1)
    _run(eng, ep1, 0.0, 10.0, content_state="ended")
    ep2 = _Clock(12.0, ev_id=2)
    _step(eng, ep2, 12.0, content_state="playing")
    assert eng.last_decision["held_sec"] == 0.0


def test_unknown_gap_does_not_advance_clock():
    eng = InterventionEngine(cooldown_seconds=0.0)
    ep = _Clock(0.0)
    _step(eng, ep, 0.0)
    for t in (2.0, 4.0, 6.0, 8.0):
        ep.now_ts = t
        eng.decide_intervention(
            distraction_event=ep, is_distracted=False, now=t, observation_state="UNKNOWN"
        )
    assert eng.last_decision["why"] == "unknown_hold"
    r = _step(eng, ep, 10.0)
    assert r is None and eng.last_decision["why"] == "too_short"


# ------------------------------------------------------- trace coverage
def test_every_skip_path_records_why():
    eng = InterventionEngine(cooldown_seconds=30.0, enabled_tiers=[])
    ep = _Clock(0.0)
    _step(eng, ep, 2.0)
    assert eng.last_decision["why"] == "too_short"
    _step(eng, ep, 8.0)
    assert eng.last_decision["why"] == "tier_disabled"

    eng = InterventionEngine(cooldown_seconds=30.0)
    ep = _Clock(0.0)
    first = _step(eng, ep, 6.0)
    assert first is not None and eng.last_decision["action"] == "fired"
    _step(eng, ep, 8.0)
    assert eng.last_decision["why"] == "pending"
    assert eng.last_decision["pending"]["tier"] == 1
    eng.record_outcome("reengaged", intervention_id=first.intervention_id, now=9.0)
    _step(eng, ep, 10.0)
    assert eng.last_decision["why"] == "cooldown"
    assert 0 < eng.last_decision["cooldown_left_sec"] <= 30.0

    eng.decide_intervention(distraction_event=None, is_distracted=False, now=50.0)
    assert eng.last_decision["why"] == "focused"
    _step(eng, ep, 51.0, coverage_ratio_30s=0.2)
    assert eng.last_decision["why"] == "low_coverage"


# ------------------------------------------------------- route level
def _start(client, app, email):
    s = _seed_student_session(app, email=email)
    h = {"Authorization": f"Bearer {s['token']}"}
    sid = client.post(
        "/api/session/start", json={"module_id": s["mod_id"], "is_monitored": True}, headers=h
    ).json["session_id"]
    return sid, h


def _backdate(app, sid, seconds):
    with app.app_context():
        ev = DistractionEvent.query.filter_by(session_id=sid, ended_at=None).first()
        ev.started_at = datetime.utcnow() - timedelta(seconds=seconds)
        db.session.commit()


def test_heartbeat_returns_intervention_debug_and_fires_while_playing(client, app):
    sid, h = _start(client, app, "p7_play@t.com")
    r = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"verdict": "DISTRACTED", "content_state": "playing"},
        headers=h,
    )
    assert r.json["intervention_debug"]["why"] == "too_short"
    _backdate(app, sid, 7)
    r = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"verdict": "DISTRACTED", "content_state": "playing"},
        headers=h,
    )
    assert r.json["intervention_triggered"] is True
    assert r.json["intervention"]["tier"] == 1
    assert r.json["intervention_debug"]["action"] == "fired"
    assert "frames_debug" in r.json


def test_heartbeat_paused_reports_grace_instead_of_silent_block(client, app):
    """Regression for session 158: paused used to block silently forever."""
    sid, h = _start(client, app, "p7_pause@t.com")
    client.post(
        f"/api/session/{sid}/heartbeat",
        json={"verdict": "DISTRACTED", "content_state": "paused", "pause_reason": "user"},
        headers=h,
    )
    _backdate(app, sid, 30)
    r = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"verdict": "DISTRACTED", "content_state": "paused", "pause_reason": "user"},
        headers=h,
    )
    assert r.json["intervention_triggered"] is False
    assert r.json["intervention_debug"]["why"] == "paused_grace"


def test_heartbeat_rejects_bad_pause_reason(client, app):
    sid, h = _start(client, app, "p7_bad@t.com")
    r = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"verdict": "DISTRACTED", "pause_reason": "nope"},
        headers=h,
    )
    assert r.status_code == 400
