"""
Adaptive Micro-Intervention Engine (PLAN 4).

- Pending prompts time out as ignored after 20 s (breaks exempt).
- Outcomes must match intervention id; noise is isolated from visual escalation.
- Cooldown starts at resolution (answer / timeout / break end), not fire time.
- Escalation memory resets only after sustained FOCUSED ≥ 10 s and never while pending.
- rule / body_no_face / absent sources capped at tier 2; tab/blur may escalate;
  tiers 3–4 require model-derived DISTRACTED.
"""
from __future__ import annotations

import itertools
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


TYPE_AMBIENT = "ambient_cue"
TYPE_PACING = "pacing_pause"
TYPE_GAMIFIED = "gamified_break"
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

PROMPT_TIMEOUT_SEC = 20.0
FOCUS_RESET_SEC = 10.0
DEFAULT_COOLDOWN_SEC = 30.0

# Sources that may not escalate past tier 2
_CAP_TIER2_SOURCES = frozenset({"rule", "body_no_face", "absent", "low_face"})
# Sources allowed to escalate (incl. beyond tier 2 when model-backed)
_TAB_SOURCES = frozenset({"tab", "blur"})
_MODEL_SOURCES = frozenset({"model6", "fusion", "model", ""})

SESSION_ENGINES: Dict[Any, "InterventionEngine"] = {}
_SESSION_ENGINE_LOCKS: Dict[Any, threading.Lock] = {}
_REGISTRY_LOCK = threading.Lock()
_ID_COUNTER = itertools.count(1)


@dataclass
class TriggeredIntervention:
    tier: int
    intervention_type: str
    message: str
    payload: Dict[str, Any] = field(default_factory=dict)
    intervention_id: Optional[str] = None
    source: str = "model"
    fired_at: float = 0.0
    deadline: Optional[float] = None


@dataclass
class _Pending:
    id: str
    tier: int
    source: str
    fired_at: float
    deadline: Optional[float]  # None = exempt (breaks)
    intervention_type: str
    is_noise: bool = False


def distraction_level_from_duration(duration_seconds: float) -> int:
    if duration_seconds < 5:
        return 0
    if duration_seconds < 10:
        return 1
    if duration_seconds < 20:
        return 2
    if duration_seconds < 40:
        return 3
    return 4


def get_session_engine(
    session_id: Any,
    cooldown_seconds: float = DEFAULT_COOLDOWN_SEC,
    enabled_tiers: Optional[List[int]] = None,
) -> InterventionEngine:
    with _REGISTRY_LOCK:
        lock = _SESSION_ENGINE_LOCKS.setdefault(session_id, threading.Lock())
    with lock:
        eng = SESSION_ENGINES.get(session_id)
        if eng is None:
            eng = InterventionEngine(
                cooldown_seconds=cooldown_seconds,
                enabled_tiers=enabled_tiers,
            )
            SESSION_ENGINES[session_id] = eng
        else:
            # Re-read cooldown settings on every evaluation
            eng.cooldown_seconds = float(cooldown_seconds)
            if enabled_tiers is not None:
                eng.enabled_tiers = set(enabled_tiers)
        return eng


def clear_session_engine(session_id: Any) -> None:
    with _REGISTRY_LOCK:
        SESSION_ENGINES.pop(session_id, None)
        _SESSION_ENGINE_LOCKS.pop(session_id, None)


class InterventionEngine:
    def __init__(
        self,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SEC,
        enabled_tiers: Optional[List[int]] = None,
        now_fn=None,
        prompt_timeout_sec: float = PROMPT_TIMEOUT_SEC,
        focus_reset_sec: float = FOCUS_RESET_SEC,
    ):
        self.cooldown_seconds = float(cooldown_seconds)
        if enabled_tiers is None:
            self.enabled_tiers = {1, 2, 3, 4}
        else:
            self.enabled_tiers = set(enabled_tiers)
        self._now = now_fn or time.time
        self.prompt_timeout_sec = float(prompt_timeout_sec)
        self.focus_reset_sec = float(focus_reset_sec)

        self.last_tier: Optional[int] = None
        self.last_outcome: Optional[str] = None
        self.last_resolved_at: Optional[float] = None  # cooldown anchor (None = never)
        self.t4_used: bool = False
        self._pending: Optional[_Pending] = None
        self._focused_since: Optional[float] = None
        self._ambient_episode_key: Optional[Any] = None  # retained for older tests
        self._lock = threading.RLock()
        self._timeout_callback = None  # optional: fn(pending) for DB logging

    @property
    def _pending_intervention(self) -> bool:
        """Back-compat for tests that poked the old boolean flag."""
        return self._pending is not None

    @_pending_intervention.setter
    def _pending_intervention(self, value: bool) -> None:
        if not value:
            self._pending = None

    # ------------------------------------------------------------------ API
    def set_timeout_callback(self, fn) -> None:
        self._timeout_callback = fn

    def tick(self, now: Optional[float] = None) -> Optional[dict]:
        """Expire pending prompts as ignored. Returns timeout record if any."""
        ts = now if now is not None else self._now()
        with self._lock:
            p = self._pending
            if p is None or p.deadline is None or ts < p.deadline:
                return None
            rec = {
                "intervention_id": p.id,
                "tier": p.tier,
                "source": p.source,
                "user_response": "timeout",
                "outcome": "ignored",
                "intervention_type": p.intervention_type,
                "is_noise": p.is_noise,
            }
            self._resolve_locked("ignored", p.id, ts, is_noise=p.is_noise)
            if self._timeout_callback:
                try:
                    self._timeout_callback(rec)
                except Exception:
                    pass
            return rec

    def record_outcome(
        self,
        outcome: str,
        intervention_id: Optional[str] = None,
        now: Optional[float] = None,
    ) -> bool:
        """Apply outcome only if id matches pending. Returns False if rejected."""
        outcome = (outcome or "").lower().strip()
        if outcome not in {"reengaged", "ignored", "ended"}:
            return False
        ts = now if now is not None else self._now()
        with self._lock:
            if self._pending is None:
                return False
            if intervention_id is not None and intervention_id != self._pending.id:
                return False
            return self._resolve_locked(
                outcome, self._pending.id, ts, is_noise=self._pending.is_noise
            )

    def _resolve_locked(
        self, outcome: str, intervention_id: str, ts: float, is_noise: bool
    ) -> bool:
        p = self._pending
        if p is None or p.id != intervention_id:
            return False
        self._pending = None
        self.last_resolved_at = ts  # cooldown starts at resolution
        if is_noise:
            # Noise never touches visual escalation memory
            return True
        self.last_outcome = outcome
        if outcome == "reengaged":
            self.last_tier = None
            self.last_outcome = "reengaged"
            self._focused_since = ts
        return True

    def reset_on_focus(self):
        """Deprecated path — use sustained focus via decide_intervention."""
        with self._lock:
            if self._pending is not None:
                return
            self.last_tier = None
            self.last_outcome = None
            self._focused_since = None

    def hold_on_unknown(self):
        return None

    def force_intervention(
        self,
        tier: int,
        is_quiz_context: bool = False,
        now: Optional[float] = None,
        source: str = "manual",
    ) -> Optional[TriggeredIntervention]:
        ts = now if now is not None else self._now()
        with self._lock:
            self.tick(ts)
            if self._pending is not None:
                return None
            if (
                self.last_resolved_at is not None
                and ts - self.last_resolved_at < self.cooldown_seconds
            ):
                return None
            resolved = self._resolve_enabled_tier(int(tier))
            if resolved is None:
                return None
            return self._fire_locked(resolved, is_quiz_context, ts, source=source)

    def decide_intervention(
        self,
        distraction_event,
        is_distracted: bool,
        is_quiz_context: bool = False,
        now: Optional[float] = None,
        wall_now: Optional[datetime] = None,
        observation_state: Optional[str] = None,
        source: str = "model",
        coverage_ratio_30s: Optional[float] = None,
        episode_clock_held: bool = False,
    ) -> Optional[TriggeredIntervention]:
        ts = now if now is not None else self._now()
        state = (observation_state or "").upper().strip()
        if not state:
            state = "DISTRACTED" if is_distracted else "FOCUSED"

        with self._lock:
            self.tick(ts)

            if state == "UNKNOWN":
                self._focused_since = None
                return self.hold_on_unknown()

            if state == "FOCUSED" or not is_distracted or distraction_event is None:
                if self._pending is not None:
                    # Never reset escalation memory while a prompt is on screen
                    return None
                if self._focused_since is None:
                    self._focused_since = ts
                elif ts - self._focused_since >= self.focus_reset_sec:
                    self.last_tier = None
                    self.last_outcome = None
                    self._focused_since = None
                return None

            # DISTRACTED
            self._focused_since = None

            if episode_clock_held:
                return None

            if self._pending is not None:
                return None

            if coverage_ratio_30s is not None and coverage_ratio_30s < 0.5:
                return None

            if (
                self.last_resolved_at is not None
                and ts - self.last_resolved_at < self.cooldown_seconds
            ):
                return None

            duration = distraction_event.duration_seconds(wall_now or datetime.utcnow())
            level = distraction_level_from_duration(duration)
            if level == 0:
                return None

            target_tier = level
            if self.last_outcome == "ignored" and self.last_tier is not None:
                target_tier = min(4, max(target_tier, self.last_tier + 1))

            target_tier = self._cap_tier_for_source(target_tier, source)
            resolved = self._resolve_enabled_tier(target_tier)
            if resolved is None:
                return None

            return self._fire_locked(resolved, is_quiz_context, ts, source=source)

    def consider_noise(
        self,
        now: Optional[float] = None,
        noise_dbfs: Optional[float] = None,
        baseline_dbfs: Optional[float] = None,
    ) -> Optional[TriggeredIntervention]:
        ts = now if now is not None else self._now()
        with self._lock:
            self.tick(ts)
            if self._pending is not None:
                return None
            if (
                self.last_resolved_at is not None
                and ts - self.last_resolved_at < self.cooldown_seconds
            ):
                return None
            if self._resolve_enabled_tier(1) is None:
                return None

            payload: Dict[str, Any] = {"trigger_source": "background_noise"}
            if noise_dbfs is not None:
                payload["noise_dbfs"] = noise_dbfs
            if baseline_dbfs is not None:
                payload["noise_baseline_dbfs"] = baseline_dbfs

            iid = self._new_id()
            deadline = ts + self.prompt_timeout_sec
            triggered = TriggeredIntervention(
                tier=1,
                intervention_type=TYPE_NOISE_NOTICE,
                message=NOISE_MESSAGE,
                payload=payload,
                intervention_id=iid,
                source="noise",
                fired_at=ts,
                deadline=deadline,
            )
            self._pending = _Pending(
                id=iid,
                tier=1,
                source="noise",
                fired_at=ts,
                deadline=deadline,
                intervention_type=TYPE_NOISE_NOTICE,
                is_noise=True,
            )
            return triggered

    def process_window(self, is_distracted: bool, timestamp: float = None) -> Optional[TriggeredIntervention]:
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

    # --------------------------------------------------------------- helpers
    def _new_id(self) -> str:
        return f"iv_{next(_ID_COUNTER)}_{uuid.uuid4().hex[:8]}"

    def _cap_tier_for_source(self, tier: int, source: str) -> int:
        src = (source or "").lower().strip()
        if src in _CAP_TIER2_SOURCES:
            return min(tier, 2)
        if src in _TAB_SOURCES:
            return tier
        if tier >= 3 and src not in _MODEL_SOURCES and src not in _TAB_SOURCES:
            # Tiers 3–4 require model-derived DISTRACTED
            return min(tier, 2)
        return tier

    def _resolve_enabled_tier(self, tier: int) -> Optional[int]:
        t = tier
        while t >= 1:
            if t in self.enabled_tiers:
                return t
            t -= 1
        return None

    def _fire_locked(
        self, tier: int, is_quiz_context: bool, ts: float, source: str = "model"
    ) -> TriggeredIntervention:
        triggered = self._select_intervention(tier, is_quiz_context)
        iid = self._new_id()
        is_break = triggered.intervention_type in {
            TYPE_SUGGEST_BREAK,
            TYPE_GAMIFIED,
        }
        deadline = None if is_break else ts + self.prompt_timeout_sec
        triggered.intervention_id = iid
        triggered.source = source
        triggered.fired_at = ts
        triggered.deadline = deadline
        self._pending = _Pending(
            id=iid,
            tier=tier,
            source=source,
            fired_at=ts,
            deadline=deadline,
            intervention_type=triggered.intervention_type,
            is_noise=False,
        )
        self.last_tier = tier
        self.last_outcome = None
        if tier == 4:
            self.t4_used = True
        return triggered

    def _select_intervention(self, tier: int, is_quiz_context: bool) -> TriggeredIntervention:
        if tier == 1:
            itype = TYPE_AMBIENT
        elif tier == 2:
            itype = TYPE_PACING
        elif tier == 3:
            itype = TYPE_HINT if is_quiz_context else TYPE_MILESTONE
        else:
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
