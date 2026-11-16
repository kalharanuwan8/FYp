"""
Evidence-rule layer (PLAN 6): the distraction criteria table as code.

One ``EvidenceTracker`` per monitored session. Each heartbeat / scored window
calls :meth:`EvidenceTracker.update` with whatever signals are available; the
tracker rates every channel NORMAL / WARNING / STRONG using the thresholds of
the criteria table, then applies the table's temporal + fusion rule:

    A. unambiguous override  - tab hidden/blurred, or left the seat
    B. >= 2 channels at >= WARNING whose patterns overlap for >= PERSIST_SEC
    C. one channel STRONG whose pattern has lasted >= SINGLE_STRONG_SEC

Pure Python, no Flask/DB. Times are seconds on any monotonic clock.
All thresholds are engineering parameters taken from the table, not clinical
cut-offs.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

NORMAL = "normal"
WARNING = "warning"
STRONG = "strong"
_RANK = {NORMAL: 0, WARNING: 1, STRONG: 2}

# Channels (rows of the criteria table). Audio is loudness-only (noise).
GAZE = "gaze"
HEAD = "head"
FACE = "face"
NOISE = "noise"
IDLE = "idle"
SKIPPING = "skipping"
QUIZ_ERRORS = "quiz_errors"
HINTS = "hints"
TAB = "tab"
CHANNELS = (GAZE, HEAD, FACE, NOISE, IDLE, SKIPPING, QUIZ_ERRORS, HINTS, TAB)

# --- "Repeatedly": >= REPEAT_MIN qualifying episodes inside REPEAT_WINDOW_SEC.
REPEAT_WINDOW_SEC = 60.0
REPEAT_MIN = 2
# A run survives missing observations (None) for this long; an explicit
# "not active" observation ends it immediately.
RUN_GAP_MAX_SEC = 2.5

# --- Webcam: gaze. Table: 1-3 s away = normal; ~3-5 s repeatedly = warning;
#     > 5 s repeatedly = strong.
GAZE_WARN_SEC = 3.0
GAZE_STRONG_SEC = 5.0
# --- Webcam: head pose. Table: few seconds = warning; > 3-4 s repeatedly = strong.
HEAD_WARN_SEC = 3.0
HEAD_STRONG_SEC = 4.0
# --- Webcam: face presence. Table: < 2 s normal; ~2-3 s = warning;
#     > 2-3 s repeatedly = strong.
FACE_WARN_SEC = 2.0
FACE_STRONG_SEC = 3.0
# Face AND body gone (left the seat): unambiguous after this long.
ABSENT_OVERRIDE_SEC = 5.0
# Any single run this long is strong on its own (upper end of "5-10 s").
CONTINUOUS_STRONG_SEC = 10.0

# --- Audio: noise spikes. Table: one-off = normal; repeated = warning;
#     repeated + gaze away / idle = strong.
NOISE_WARN_SPIKES = 3
# --- Interaction: idle. Table: ~8-10 s = warning; > 10 s + gaze/head away = strong.
IDLE_WARN_SEC = 8.0
IDLE_STRONG_SEC = 10.0
# --- Interaction: fast skipping (video forward seeks).
SKIP_WARN_EVENTS = 2
# --- Interaction: error streak / repeated hints (quiz).
QUIZ_ERROR_WARN_STREAK = 3
HINT_REPEAT_WARN = 2
# --- Browser: tab hidden / window blurred (unchanged from PLAN 4).
TAB_HIDDEN_SEC = 3.0
WINDOW_BLUR_SEC = 5.0

# --- Temporal + fusion rule.
PERSIST_SEC = 5.0
SINGLE_STRONG_SEC = CONTINUOUS_STRONG_SEC
DEFAULT_ENTER_PROB = 0.6
# Rule-layer probability (fused with the model as max(p_model, p_rules)).
P_RULES_ONE_WARNING = 0.5
P_RULES_MULTI = 0.7
P_RULES_STRONG = 0.9

RULE_A_TAB = "A_tab"
RULE_A_ABSENT = "A_absent"
RULE_B_MULTI = "B_multi_signal"
RULE_C_STRONG = "C_single_strong"

DISTRACTED = "DISTRACTED"
FOCUSED = "FOCUSED"


@dataclass
class _Run:
    """A continuous "condition active" run with a history of finished episodes."""

    warn_sec: float
    start: Optional[float] = None
    last_seen: Optional[float] = None
    episodes: Deque[float] = field(default_factory=deque)  # end times of qualifying runs

    def update(self, t: float, active: Optional[bool], dwell_sec: Optional[float] = None) -> None:
        if active is None:
            if self.start is not None and self.last_seen is not None:
                if t - self.last_seen > RUN_GAP_MAX_SEC:
                    self._close(self.last_seen)
            return
        if not active:
            if self.start is not None:
                self._close(self.last_seen if self.last_seen is not None else t)
            return
        if self.start is None or (
            self.last_seen is not None and t - self.last_seen > RUN_GAP_MAX_SEC
        ):
            if self.start is not None:
                self._close(self.last_seen)
            self.start = t
        if dwell_sec is not None and dwell_sec > 0:
            self.start = min(self.start, t - float(dwell_sec))
        self.last_seen = t

    def _close(self, end: Optional[float]) -> None:
        if self.start is not None and end is not None and end - self.start >= self.warn_sec:
            self.episodes.append(end)
        self.start = None
        self.last_seen = None

    def length(self, t: float) -> float:
        return 0.0 if self.start is None else max(0.0, t - self.start)

    def prior_episodes(self, t: float) -> int:
        while self.episodes and t - self.episodes[0] > REPEAT_WINDOW_SEC:
            self.episodes.popleft()
        return len(self.episodes)

    def reset(self) -> None:
        self.start = None
        self.last_seen = None
        self.episodes.clear()


@dataclass
class EvidenceResult:
    verdict: str
    rule: Optional[str]
    levels: Dict[str, str]
    p_rules: float
    p_fused: Optional[float]
    pattern_sec: Dict[str, float]
    reasons: List[str]

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "rule": self.rule,
            "evidence": dict(self.levels),
            "p_rules": round(self.p_rules, 4),
            "p_fused": None if self.p_fused is None else round(self.p_fused, 4),
            "pattern_sec": {k: round(v, 2) for k, v in self.pattern_sec.items()},
            "reasons": list(self.reasons),
        }


class EvidenceTracker:
    """Per-session state for the criteria-table rules."""

    def __init__(self) -> None:
        self._gaze = _Run(GAZE_WARN_SEC)
        self._head = _Run(HEAD_WARN_SEC)
        self._face = _Run(FACE_WARN_SEC)
        self._absent = _Run(ABSENT_OVERRIDE_SEC)
        self._noise_spikes: Deque[float] = deque()
        self._seek_events: Deque[float] = deque()
        # When each channel first reached >= WARNING in its current pattern.
        self._warn_since: Dict[str, Optional[float]] = {c: None for c in CHANNELS}
        self._strong_since: Dict[str, Optional[float]] = {c: None for c in CHANNELS}

    def reset(self) -> None:
        self.__init__()

    # ------------------------------------------------------------------ update
    def update(
        self,
        t: float,
        *,
        gaze_off: Optional[bool] = None,
        gaze_off_dwell_sec: Optional[float] = None,
        head_away: Optional[bool] = None,
        face_present: Optional[bool] = None,
        body_present: Optional[bool] = None,
        noise_spike: Optional[bool] = None,
        idle_sec: Optional[float] = None,
        video_playing: bool = False,
        seek_forward_events: int = 0,
        quiz_wrong_streak: Optional[int] = None,
        hint_repeats: Optional[int] = None,
        tab_hidden_sec: Optional[float] = None,
        window_blur_sec: Optional[float] = None,
        p_model: Optional[float] = None,
        enter_prob: float = DEFAULT_ENTER_PROB,
    ) -> EvidenceResult:
        t = float(t)
        absent = None
        face_missing = None
        if face_present is not None:
            face_missing = not face_present
            if body_present is not None:
                absent = (not face_present) and (not body_present)
        # Gaze / head are unobservable without a face: keep runs alive briefly.
        if face_present is False:
            gaze_off = None if gaze_off is False else gaze_off
            head_away = None if head_away is False else head_away

        self._gaze.update(t, gaze_off, gaze_off_dwell_sec if gaze_off else None)
        self._head.update(t, head_away)
        self._face.update(t, face_missing)
        self._absent.update(t, absent)

        if noise_spike:
            self._noise_spikes.append(t)
        for _ in range(max(0, int(seek_forward_events or 0))):
            self._seek_events.append(t)
        for dq in (self._noise_spikes, self._seek_events):
            while dq and t - dq[0] > REPEAT_WINDOW_SEC:
                dq.popleft()

        levels: Dict[str, str] = {}
        pattern_start: Dict[str, Optional[float]] = {}
        reasons: List[str] = []

        # ---- run-based webcam channels
        for name, run, warn, strong in (
            (GAZE, self._gaze, GAZE_WARN_SEC, GAZE_STRONG_SEC),
            (HEAD, self._head, HEAD_WARN_SEC, HEAD_STRONG_SEC),
            (FACE, self._face, FACE_WARN_SEC, FACE_STRONG_SEC),
        ):
            levels[name], pattern_start[name] = self._run_level(run, t, warn, strong)

        visual_away = _RANK[levels[GAZE]] >= 1 or _RANK[levels[HEAD]] >= 1

        # ---- idle (ignored while lesson video plays: no input is expected)
        idle_lvl = NORMAL
        idle_start = None
        if idle_sec is not None and not video_playing and idle_sec >= IDLE_WARN_SEC:
            idle_lvl = WARNING
            idle_start = t - float(idle_sec)
            if idle_sec > IDLE_STRONG_SEC and visual_away:
                idle_lvl = STRONG
        levels[IDLE], pattern_start[IDLE] = idle_lvl, idle_start
        attention_away = visual_away or idle_lvl != NORMAL

        # ---- event / count channels
        levels[NOISE] = NORMAL
        if len(self._noise_spikes) >= NOISE_WARN_SPIKES:
            levels[NOISE] = STRONG if attention_away else WARNING
        levels[SKIPPING] = NORMAL
        if len(self._seek_events) >= SKIP_WARN_EVENTS:
            levels[SKIPPING] = STRONG if visual_away else WARNING
        levels[QUIZ_ERRORS] = NORMAL
        if quiz_wrong_streak is not None and quiz_wrong_streak >= QUIZ_ERROR_WARN_STREAK:
            levels[QUIZ_ERRORS] = STRONG if attention_away else WARNING
        levels[HINTS] = NORMAL
        if hint_repeats is not None and hint_repeats >= HINT_REPEAT_WARN:
            levels[HINTS] = STRONG if attention_away else WARNING
        for name in (NOISE, SKIPPING, QUIZ_ERRORS, HINTS):
            pattern_start[name] = None  # filled from _warn_since below

        # ---- browser tab / blur
        tab_lvl = NORMAL
        tab_start = None
        if tab_hidden_sec is not None and tab_hidden_sec >= TAB_HIDDEN_SEC:
            tab_lvl, tab_start = STRONG, t - float(tab_hidden_sec)
            reasons.append("tab_hidden")
        elif window_blur_sec is not None and window_blur_sec >= WINDOW_BLUR_SEC:
            tab_lvl, tab_start = STRONG, t - float(window_blur_sec)
            reasons.append("window_blur")
        levels[TAB], pattern_start[TAB] = tab_lvl, tab_start

        # ---- pattern start times (for persistence)
        for c in CHANNELS:
            lvl = levels[c]
            if _RANK[lvl] >= 1:
                since = pattern_start.get(c)
                prev = self._warn_since[c]
                if since is None:
                    since = prev if prev is not None else t
                elif prev is not None:
                    since = min(since, prev)
                self._warn_since[c] = since
            else:
                self._warn_since[c] = None
            if lvl == STRONG:
                if self._strong_since[c] is None:
                    self._strong_since[c] = self._warn_since[c]
            else:
                self._strong_since[c] = None

        pattern_sec = {
            c: t - self._warn_since[c] for c in CHANNELS if self._warn_since[c] is not None
        }

        # ---- rule-layer probability
        n_warn = sum(1 for c in CHANNELS if _RANK[levels[c]] >= 1)
        any_strong = any(levels[c] == STRONG for c in CHANNELS)
        if any_strong:
            p_rules = P_RULES_STRONG
        elif n_warn >= 2:
            p_rules = P_RULES_MULTI
        elif n_warn == 1:
            p_rules = P_RULES_ONE_WARNING
        else:
            p_rules = 0.0
        p_fused = None if p_model is None else max(float(p_model), p_rules)
        p_decide = p_rules if p_fused is None else p_fused

        # ---- decision
        rule = None
        absent_sec = self._absent.length(t)
        if tab_lvl == STRONG:
            rule = RULE_A_TAB
        elif absent_sec >= ABSENT_OVERRIDE_SEC:
            rule = RULE_A_ABSENT
            reasons.append("absent")
        else:
            persisted = [c for c, s in pattern_sec.items() if s >= PERSIST_SEC]
            if len(persisted) >= 2 and p_decide >= enter_prob:
                rule = RULE_B_MULTI
                reasons.append("multi_signal:" + "+".join(sorted(persisted)))
            else:
                for c in CHANNELS:
                    s0 = self._strong_since[c]
                    if s0 is not None and t - s0 >= SINGLE_STRONG_SEC:
                        rule = RULE_C_STRONG
                        reasons.append("single_strong:" + c)
                        break

        return EvidenceResult(
            verdict=DISTRACTED if rule else FOCUSED,
            rule=rule,
            levels=levels,
            p_rules=p_rules,
            p_fused=p_fused,
            pattern_sec=pattern_sec,
            reasons=reasons,
        )

    @staticmethod
    def _run_level(run: _Run, t: float, warn: float, strong: float):
        length = run.length(t)
        if run.start is None or length < warn:
            return NORMAL, None
        repeated = run.prior_episodes(t) + 1 >= REPEAT_MIN
        if length >= CONTINUOUS_STRONG_SEC or (length > strong and repeated):
            return STRONG, run.start
        return WARNING, run.start
