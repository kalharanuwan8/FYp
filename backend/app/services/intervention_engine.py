"""
Adaptive Micro-Intervention Engine.

Severity is derived from how long an open distraction episode has been running.
Escalation advances one tier when the previous intervention was ignored.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any


# Canonical intervention_type values
TYPE_AMBIENT = "ambient_cue"
TYPE_PACING = "pacing_pause"
TYPE_GAMIFIED = "gamified_break"  # legacy timer; content Tier 3 now prefers milestone_quiz
TYPE_MILESTONE = "milestone_quiz"
TYPE_HINT = "hint_injection"
TYPE_PACING_REDUCTION = "content_pacing_reduction"
TYPE_SUGGEST_BREAK = "suggest_break"
TYPE_NOISE_NOTICE = "environment_noise_notice"

MESSAGES = {
    TYPE_AMBIENT: "Let's refocus together!",
    TYPE_PACING: "Still with me? Tap to continue.",
    TYPE_GAMIFIED: "Quick 10s focus check-in!",
    TYPE_MILESTONE: "Quick checkpoint — answer to continue.",
    TYPE_HINT: "Here's a quick hint to get you unstuck.",
    TYPE_PACING_REDUCTION: "We'll slow the pace a bit so you can catch up.",
    TYPE_SUGGEST_BREAK: "Great effort! Time for a short break.",
}

NOISE_MESSAGE = "It's quite noisy where you are — that can make it hard to concentrate."


@dataclass
class TriggeredIntervention:
    tier: int
    intervention_type: str
    message: str
    payload: Dict[str, Any] = field(default_factory=dict)


def distraction_level_from_duration(duration_seconds: float) -> int:
    """Map open-episode duration to distraction level 0–4."""
    if duration_seconds < 5:
        return 0
    if duration_seconds < 10:
        return 1
    if duration_seconds < 20:
        return 2
    if duration_seconds < 40:
        return 3
    return 4


class InterventionEngine:
    """
    Per-session in-memory escalation state.
    Call decide_intervention() on each heartbeat after episode open/close.
    """

    def __init__(
        self,
        cooldown_seconds: float = 30.0,
        enabled_tiers: Optional[List[int]] = None,
        now_fn=None,
    ):
        self.cooldown_seconds = float(cooldown_seconds)
        # None → default all tiers. Explicit [] → no interventions (do not coerce).
        if enabled_tiers is None:
            self.enabled_tiers = {1, 2, 3, 4}
        else:
            self.enabled_tiers = set(enabled_tiers)
        self._now = now_fn or time.time

        self.last_tier: Optional[int] = None
        self.last_outcome: Optional[str] = None  # reengaged | ignored | ended
        self.last_intervention_at: float = 0.0
        self.t4_used: bool = False
        self._pending_intervention: bool = False  # waiting for outcome

    def record_outcome(self, outcome: str):
        outcome = (outcome or "").lower().strip()
        if outcome not in {"reengaged", "ignored", "ended"}:
            return
        self.last_outcome = outcome
        self._pending_intervention = False
        if outcome == "reengaged":
            self.last_tier = None
            self.last_outcome = "reengaged"

    def reset_on_focus(self):
        """Full de-escalate when verdict flips to focused (confirmed re-engagement)."""
        self.last_tier = None
        self.last_outcome = None
        self._pending_intervention = False

    def hold_on_unknown(self):
        """
        UNKNOWN observations: do not escalate visual distraction and do not
        fabricate a student outcome. Pending interventions and cooldown clocks
        stay as-is until FOCUSED (reset) or an explicit record_outcome.
        """
        return None

    def force_intervention(
        self,
        tier: int,
        is_quiz_context: bool = False,
        now: Optional[float] = None,
    ) -> Optional[TriggeredIntervention]:
        """Manually fire a tier, bypassing duration/cooldown. Still blocks if one is pending."""
        ts = now if now is not None else self._now()
        if self._pending_intervention:
            return None
        resolved_tier = self._resolve_enabled_tier(int(tier))
        if resolved_tier is None:
            return None
        triggered = self._select_intervention(resolved_tier, is_quiz_context)
        self.last_intervention_at = ts
        self.last_tier = resolved_tier
        self.last_outcome = None
        self._pending_intervention = True
        if resolved_tier == 4:
            self.t4_used = True
        return triggered

    def decide_intervention(
        self,
        distraction_event,
        is_distracted: bool,
        is_quiz_context: bool = False,
        now: Optional[float] = None,
        wall_now: Optional[datetime] = None,
        observation_state: Optional[str] = None,
    ) -> Optional[TriggeredIntervention]:
        """
        Decide visual intervention from the current observation.

        Pass ``observation_state`` explicitly. Do not rely on
        ``is_distracted=False`` alone for UNKNOWN — that path historically
        invoked focus-reset and would fabricate re-engagement.
        """
        ts = now if now is not None else self._now()
        state = (observation_state or "").upper().strip()
        if not state:
            state = "DISTRACTED" if is_distracted else "FOCUSED"

        if state == "UNKNOWN":
            return self.hold_on_unknown()

        if state != "DISTRACTED" or not is_distracted or distraction_event is None:
            self.reset_on_focus()
            return None

        # Still waiting for student response — do not stack interventions
        if self._pending_intervention:
            return None

        if ts - self.last_intervention_at < self.cooldown_seconds:
            return None

        duration = distraction_event.duration_seconds(wall_now or datetime.utcnow())
        level = distraction_level_from_duration(duration)
        if level == 0:
            return None

        target_tier = level

        # Escalate one tier if previous intervention was ignored
        if self.last_outcome == "ignored" and self.last_tier is not None:
            target_tier = min(4, max(target_tier, self.last_tier + 1))

        resolved_tier = self._resolve_enabled_tier(target_tier)
        if resolved_tier is None:
            return None

        triggered = self._select_intervention(resolved_tier, is_quiz_context)
        self.last_intervention_at = ts
        self.last_tier = resolved_tier
        self.last_outcome = None
        self._pending_intervention = True
        if resolved_tier == 4:
            self.t4_used = True
        return triggered

    def consider_noise(
        self,
        now: Optional[float] = None,
        noise_dbfs: Optional[float] = None,
        baseline_dbfs: Optional[float] = None,
    ) -> Optional[TriggeredIntervention]:
        """
        Fire the tier-1 environment noise notice for sustained background noise.

        Noise is an environment problem, not student behaviour, so this
        deliberately does NOT touch ``last_tier`` / ``last_outcome`` /
        ``t4_used``: ignoring a noise cue must not escalate the next visual
        intervention, and a noisy room must never climb to "suggest break".
        It does share the pending lock and cooldown so cues never stack.
        """
        ts = now if now is not None else self._now()

        if self._pending_intervention:
            return None
        if ts - self.last_intervention_at < self.cooldown_seconds:
            return None
        if self._resolve_enabled_tier(1) is None:
            return None

        payload: Dict[str, Any] = {"trigger_source": "background_noise"}
        if noise_dbfs is not None:
            payload["noise_dbfs"] = noise_dbfs
        if baseline_dbfs is not None:
            payload["noise_baseline_dbfs"] = baseline_dbfs

        triggered = TriggeredIntervention(
            tier=1,
            intervention_type=TYPE_NOISE_NOTICE,
            message=NOISE_MESSAGE,
            payload=payload,
        )
        self.last_intervention_at = ts
        self._pending_intervention = True
        return triggered

    # Back-compat alias used by older call sites / socket stub
    def process_window(self, is_distracted: bool, timestamp: float = None) -> Optional[TriggeredIntervention]:
        """
        Legacy window API — synthesizes a short fake duration so debounce-like
        behaviour still works when no episode object is available.
        Prefer decide_intervention() with a real DistractionEvent.
        """
        class _Fake:
            def __init__(self, start):
                self.started_at = start
                self.ended_at = None

            def duration_seconds(self, now=None):
                return 8.0 if is_distracted else 0.0

        fake = _Fake(datetime.utcnow()) if is_distracted else None
        return self.decide_intervention(
            distraction_event=fake,
            is_distracted=is_distracted,
            is_quiz_context=False,
            now=timestamp,
            observation_state="DISTRACTED" if is_distracted else "FOCUSED",
        )

    def _resolve_enabled_tier(self, tier: int) -> Optional[int]:
        """Fall back one tier at a time if the computed tier is disabled."""
        t = tier
        while t >= 1:
            if t in self.enabled_tiers:
                return t
            t -= 1
        return None

    def _select_intervention(self, tier: int, is_quiz_context: bool) -> TriggeredIntervention:
        if tier == 1:
            itype = TYPE_AMBIENT
        elif tier == 2:
            itype = TYPE_PACING
        elif tier == 3:
            itype = TYPE_HINT if is_quiz_context else TYPE_MILESTONE
        else:
            # Tier 4: first severe → pacing reduction; further → suggest break
            itype = TYPE_SUGGEST_BREAK if self.t4_used else TYPE_PACING_REDUCTION

        payload: Dict[str, Any] = {}
        if itype == TYPE_HINT:
            payload = {
                "generated_question": "What is the main idea of the section you just read?",
                "hint_text": "Skim the heading and first sentence of the current section.",
            }
        elif itype == TYPE_MILESTONE:
            payload = {
                "generated_question": "What is the main idea of this material?",
                "options": [
                    "The core concept from the lesson",
                    "An unrelated topic",
                    "A homework deadline",
                    "None of the above",
                ],
                "hint_text": "Skim the summary for the key idea.",
            }
        elif itype == TYPE_GAMIFIED:
            payload = {"break_seconds": 12}
        elif itype == TYPE_PACING_REDUCTION:
            payload = {"pacing_factor": 0.75}

        return TriggeredIntervention(
            tier=tier,
            intervention_type=itype,
            message=MESSAGES[itype],
            payload=payload,
        )
