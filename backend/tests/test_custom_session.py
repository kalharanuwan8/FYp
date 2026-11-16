"""Custom uploads run the monitoring pipeline with the fixed best interventions."""
import io
from datetime import datetime, timedelta

from app.db_models import DistractionEvent
from app.extensions import db
from app.services.intervention_engine import POLICY_BEST, InterventionEngine
from tests.test_intervention_plan7 import _Clock, _run, _step
from tests.test_session import _seed_student_session


def test_best_policy_skips_quiz_and_uses_a_break_when_distraction_is_long():
    eng = InterventionEngine(cooldown_seconds=0.0, policy=POLICY_BEST)
    ep = _Clock(0.0)
    short = _run(eng, ep, 0.0, 8.0, content_state="playing")
    assert short[0][1].intervention_type == "ambient_cue"
    eng.record_outcome("reengaged", intervention_id=short[0][1].intervention_id, now=8.0)

    ep2 = _Clock(20.0, ev_id=2)
    # Episode is already 25 s old at the first beat (started at t=0 of this clock's wall).
    ep2.start_ts = 0.0
    fired = _step(eng, ep2, 25.0, content_state="playing")
    assert fired is not None
    assert fired.intervention_type == "suggest_break"
    assert fired.tier == 4


def test_course_policy_still_uses_a_milestone_at_tier_3():
    eng = InterventionEngine(cooldown_seconds=0.0)
    ep = _Clock(-25.0)
    fired = _step(eng, ep, 0.0, content_state="playing")
    assert fired is not None
    assert fired.intervention_type == "milestone_quiz"


def _auth(client, app, email):
    seeded = _seed_student_session(app, email=email)
    return {"Authorization": f"Bearer {seeded['token']}"}


def test_upload_and_start_custom_session(client, app):
    headers = _auth(client, app, "custom_up@t.com")
    bad = client.post(
        "/api/session/custom/uploads",
        data={"file": (io.BytesIO(b"MZ"), "virus.exe")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert bad.status_code == 400

    up = client.post(
        "/api/session/custom/uploads",
        data={"file": (io.BytesIO(b"%PDF-1.4 notes"), "my notes.pdf"), "title": "Revision"},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert up.status_code == 201
    assert up.json["content_kind"] == "document"
    assert up.json["title"] == "Revision"

    listed = client.get("/api/session/custom/uploads", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json["uploads"]) == 1

    started = client.post(
        "/api/session/custom/start",
        json={"upload_id": up.json["id"]},
        headers=headers,
    )
    assert started.status_code == 201
    assert started.json["session_kind"] == "custom"
    assert started.json["interventions"] == "best"
    sid = started.json["session_id"]

    forced = client.post(
        f"/api/session/{sid}/trigger-intervention",
        json={"tier": 3},
        headers=headers,
    )
    assert forced.status_code == 403
    assert forced.json["intervention_triggered"] is False

    beat = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"verdict": "DISTRACTED", "content_state": "playing"},
        headers=headers,
    )
    assert beat.status_code == 200
    assert beat.json["intervention_triggered"] is False

    with app.app_context():
        ev = DistractionEvent.query.filter_by(session_id=sid, ended_at=None).first()
        ev.started_at = datetime.utcnow() - timedelta(seconds=25)
        db.session.commit()

    beat = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"verdict": "DISTRACTED", "content_state": "playing"},
        headers=headers,
    )
    assert beat.json["intervention_triggered"] is True
    assert beat.json["intervention"]["intervention_type"] == "suggest_break"

    paused = client.post(
        f"/api/session/{sid}/heartbeat",
        json={"verdict": "DISTRACTED", "content_state": "paused", "pause_reason": "user"},
        headers=headers,
    )
    assert paused.json["intervention_triggered"] is False
