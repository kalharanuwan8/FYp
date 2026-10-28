"""
InterventionEngine behaviour under default settings. Does not modify engine code.

  venvpy312\\Scripts\\python.exe evaluation\\thesis_numbers\\run_intervention.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.intervention_engine import InterventionEngine

OUT = Path(__file__).resolve().parent / "raw"
OUT.mkdir(parents=True, exist_ok=True)

BASE_NOW = 1_700_000_000.0  # far above cooldown, like time.time()
WALL0 = datetime(2026, 1, 1, 0, 0, 0)


class Episode:
    """Same duration formula as DistractionEvent.duration_seconds."""

    def __init__(self, started_at: datetime):
        self.started_at = started_at
        self.ended_at = None

    def duration_seconds(self, now=None) -> float:
        end = self.ended_at or now or datetime.utcnow()
        if not self.started_at:
            return 0.0
        return max(0.0, (end - self.started_at).total_seconds())


def simulate(label: str, response: str | None, base_now: float) -> dict:
    engine = InterventionEngine(cooldown_seconds=30.0, enabled_tiers=None)
    episode = Episode(WALL0)
    fires = []
    heartbeats = []
    pending_after = None
    for t in range(0, 121, 2):
        if response is not None and fires:
            last = fires[-1]
            if t == last["second"] + 2 and engine._pending_intervention:
                before = engine._pending_intervention
                engine.record_outcome(response)
                heartbeats.append(
                    {
                        "second": t,
                        "event": "record_outcome",
                        "response": response,
                        "pending_before": before,
                        "pending_after": engine._pending_intervention,
                        "last_outcome": engine.last_outcome,
                        "last_tier": engine.last_tier,
                    }
                )
        triggered = engine.decide_intervention(
            distraction_event=episode,
            is_distracted=True,
            is_quiz_context=False,
            now=base_now + t,
            wall_now=WALL0 + timedelta(seconds=t),
            observation_state="DISTRACTED",
        )
        row = {
            "second": t,
            "duration_seconds": episode.duration_seconds(WALL0 + timedelta(seconds=t)),
            "pending_before_decide": None,
            "fired": triggered is not None,
        }
        if triggered is not None:
            fires.append(
                {
                    "second": t,
                    "tier": int(triggered.tier),
                    "intervention_type": triggered.intervention_type,
                }
            )
            row["tier"] = int(triggered.tier)
            row["intervention_type"] = triggered.intervention_type
        heartbeats.append(row)
    return {
        "label": label,
        "response": response,
        "base_now": base_now,
        "cooldown_seconds": engine.cooldown_seconds,
        "enabled_tiers": sorted(engine.enabled_tiers),
        "n_heartbeats": len([h for h in heartbeats if "fired" in h]),
        "interventions": fires,
        "trace": heartbeats,
        "pending_at_end": engine._pending_intervention,
        "last_tier_at_end": engine.last_tier,
        "last_outcome_at_end": engine.last_outcome,
        "last_intervention_at_end": engine.last_intervention_at,
    }


def cooldown_zero_check() -> dict:
    """Does last_intervention_at == 0 skip the cooldown comparison?"""
    episode = Episode(WALL0)
    # duration 8 s so level is 1 if the cooldown does not return first
    wall = WALL0 + timedelta(seconds=8)

    eng_small = InterventionEngine(cooldown_seconds=30.0)
    small = eng_small.decide_intervention(
        distraction_event=episode,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=10.0,
        wall_now=wall,
    )
    eng_large = InterventionEngine(cooldown_seconds=30.0)
    large = eng_large.decide_intervention(
        distraction_event=episode,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW,
        wall_now=wall,
    )
    # default now_fn is time.time(), which is large. One call, no explicit now.
    eng_default = InterventionEngine(cooldown_seconds=30.0)
    default = eng_default.decide_intervention(
        distraction_event=episode,
        is_distracted=True,
        observation_state="DISTRACTED",
        wall_now=wall,
    )
    return {
        "field_name_in_code": "last_intervention_at",
        "initial_value": 0.0,
        "there_is_no_field_named_last_triggered_at": True,
        "comparison": "if ts - self.last_intervention_at < self.cooldown_seconds: return None",
        "now_10_with_duration_8s": None
        if small is None
        else {"tier": small.tier, "type": small.intervention_type},
        "pending_after_now_10": eng_small._pending_intervention,
        "now_1700000000_with_duration_8s": None
        if large is None
        else {"tier": large.tier, "type": large.intervention_type},
        "default_time_time_with_duration_8s": None
        if default is None
        else {"tier": default.tier, "type": default.intervention_type},
        "default_last_intervention_at_after": eng_default.last_intervention_at,
    }


def tiers_3_4_at_6s() -> dict:
    engine = InterventionEngine(cooldown_seconds=30.0, enabled_tiers=[3, 4])
    episode = Episode(WALL0)
    triggered = engine.decide_intervention(
        distraction_event=episode,
        is_distracted=True,
        observation_state="DISTRACTED",
        now=BASE_NOW + 6,
        wall_now=WALL0 + timedelta(seconds=6),
    )
    return {
        "enabled_tiers": sorted(engine.enabled_tiers),
        "duration_seconds": episode.duration_seconds(WALL0 + timedelta(seconds=6)),
        "fired": None
        if triggered is None
        else {"tier": int(triggered.tier), "intervention_type": triggered.intervention_type},
        "pending_after": engine._pending_intervention,
    }


def main() -> None:
    result = {
        "a_no_response_wallclock_base": simulate("no_response", None, BASE_NOW),
        "b_acknowledged_2s_after_wallclock_base": simulate(
            "acknowledged", "acknowledged", BASE_NOW
        ),
        "extra_ignored_2s_after_wallclock_base": simulate(
            "ignored", "ignored", BASE_NOW
        ),
        "extra_reengaged_2s_after_wallclock_base": simulate(
            "reengaged", "reengaged", BASE_NOW
        ),
        "a_no_response_clock_starting_at_0": simulate("no_response_clock0", None, 0.0),
        "cooldown_when_last_intervention_at_is_0": cooldown_zero_check(),
        "enabled_tiers_3_4_episode_6s": tiers_3_4_at_6s(),
    }
    path = OUT / "intervention.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"WROTE {path}")
    print("A fires", result["a_no_response_wallclock_base"]["interventions"])
    print("B fires", result["b_acknowledged_2s_after_wallclock_base"]["interventions"])
    print("A clock0 fires", result["a_no_response_clock_starting_at_0"]["interventions"])
    print("tiers 3,4 @ 6s", result["enabled_tiers_3_4_episode_6s"])
    print("cooldown check", result["cooldown_when_last_intervention_at_is_0"])


if __name__ == "__main__":
    main()
