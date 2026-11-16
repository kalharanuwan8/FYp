# PLAN 7: Why interventions don't fire, plus an evaluation terminal overlay

Status: proposed (2026-11-15). Independent of PLAN 6 step 2. The terminal is designed to show PLAN 6
evidence channels once those land.

## 1. Root cause (verified)

### Evidence from the live DB (session 158, 2026-11-15 02:35, subject 10)

- 111 observations at a steady 2.0 s heartbeat (p90 2.02 s, max 2.9 s).
- 93 DISTRACTED observations, including one continuous run of 94 s; the stored episodes are 10 s, 78 s and 96 s.
- `intervention_logs` for the session is empty, so the engine **never fired once**.
- Subject 10 has all four tiers enabled, cooldown is 20 s, and nothing was pending. So tier config, cooldown
  and pending prompts are ruled out.

### Reproduction (Flask test client, same 30 s DISTRACTED episode, only `content_state` varied)

| content_state | intervention |
|---|---|
| `playing` | fired, **tier 3** |
| `none` | fired, **tier 3** |
| `paused` | **nothing** |
| `ended` | **nothing** |

### Bug 1: a paused or ended video silently blocks every intervention

`backend/app/routes/session.py` (heartbeat):
```python
episode_held = content_state in {"paused", "ended"}
```
`VideoLearningPlayer.jsx` sets `paused` on **every** pause: the student pausing, the intervention
pausing the video, `resumeIfWasPlaying()` when the video wasn't playing, and the video ending. Meanwhile
the camera keeps classifying, so Focus buddy turns amber, but the engine returns `None`. The UI and the engine
disagree, which is exactly what you saw.

### Bug 2: the held clock isn't actually held, so the first nudge jumps to tier 3

The episode duration is wall-clock (`DistractionEvent.duration_seconds = now - started_at`). The hold
blocks firing but doesn't stop the clock. When the video resumes, the episode is already 20 s+ old, so
the first intervention is **tier 3** (the repro fired T3 at 30 s), skipping T1 and T2. That also reads as
"not the expected intervention".

### Bug 3 (smaller): two sessions are created per start

Sessions 155/156 and 157/158 started in the same millisecond, and 157 never ended. This is the React StrictMode
double-mount in `VideoLearningPlayer.jsx` → `startMonitoredSession`. It's harmless for interventions, because
heartbeats go to one session, but it leaves orphan open sessions and skews analytics.

### Why this was hard to see

The heartbeat response returns `intervention_triggered: false` with **no reason**. The engine has 7
silent exits: UNKNOWN, focused, held, pending, coverage, cooldown, and level 0 (<5 s).

## 2. Fixes

### 2.1 Pause handling (`session.py`, `intervention_engine.py`)

Replace the blanket hold with a pause grace:

- `PAUSE_GRACE_SEC = 10`: a student who pauses to take notes isn't nudged for the first 10 s of the pause.
- After the grace, a paused + DISTRACTED student **can** be nudged, but capped at **tier 2** (a gentle
  "ready to continue?" cue). There's no milestone quiz or content-pacing change on a paused video.
- `ended`: no visual interventions, and Focus buddy shows neutral ("lesson finished") instead of amber.
- A **pending prompt** still holds (unchanged). That pause is caused by the system, not the student.
- Send `pause_reason: "user" | "intervention" | "ended"` from the player. Only `"user"` gets the grace
  logic; `"intervention"` is covered by the pending hold.

### 2.2 Honest episode clock (`intervention_engine.py`)

- The engine tracks `held_seconds` for the open episode, accumulated on held heartbeats using the previous
  heartbeat delta, capped at `EPISODE_GAP_MAX`.
- `effective_duration = wall_duration - held_seconds` feeds `distraction_level_from_duration`.
- The result is that escalation always starts at T1 for a new episode, unless the "ignored → +1 tier" rule applies.
- Reset `held_seconds` when an episode closes or a new one opens. Key it by `distraction_event.id`.

### 2.3 Decision trace (`intervention_engine.py`)

`decide_intervention` records `self.last_decision`, a dict with:

```
{ "action": "fired" | "skip",
  "why": "unknown_hold" | "focused" | "paused_grace" | "ended" | "pending" | "low_coverage"
         | "cooldown" | "too_short" | "tier_disabled" | "fired",
  "episode_sec": 7.9, "held_sec": 0.0, "level": 1, "tier": 1,
  "cooldown_left_sec": 0.0, "pending": {"tier":1, "left_sec":2.1} | null }
```

The heartbeat returns it as `intervention_debug`. It's additive, so existing keys are unchanged.

### 2.4 Duplicate session start (`VideoLearningPlayer.jsx` / `useMonitoringSession.js`)

Add a module-level in-flight promise per `module_id` in `startMonitoredSession`. A second call during
StrictMode remount awaits the first instead of POSTing `/start` again.

## 3. Evaluation terminal overlay

A monospaced, terminal-style log drawn **over the video stage** (inside `stageRef`, so it also shows in
fullscreen). Someone evaluating the system can read, heartbeat by heartbeat, what the model saw, what it
decided, and what the intervention engine did with it.

### 3.1 Where and when it shows

- New `frontend/src/components/student/EvalTerminal.jsx`, rendered inside the stage in `VideoLearningPlayer`.
  It's available when `demo_mode` is on (existing `/session/demo-config`) **or** the URL has `?eval=1`.
- Toggle with the backtick key `` ` `` or a small `>_` button. It's off by default for students.
- Semi-transparent, bottom-left, resizable height, `pointer-events` only on its own toolbar, so the video
  and prompts stay usable. It sits below the intervention overlay in z-order.

### 3.2 What each heartbeat line shows (plain language first, numbers second)

```
02:35:41  DISTRACTED  looking away from screen 3.4s · head turned left 21°
          model p=0.74 · gaze p=0.90 · fused 0.90 ≥ 0.60 → source gaze_screen · face 100% (9/9 frames)
          episode 7.9s → level 1 → FIRED T1 ambient cue (iv_12)
02:35:43  DISTRACTED  looking away 5.4s
          episode 9.9s → no prompt: T1 still on screen (4.1s left)
02:35:45  DISTRACTED  tab hidden 3.0s (browser) → override
          episode 11.9s → no prompt: cooldown 14s left
02:35:47  UNKNOWN     face not visible, body present (2/9 frames with face)
02:35:49  FOCUSED     on screen · p=0.12
```

Color: FOCUSED is green, DISTRACTED amber, UNKNOWN grey, FIRED cyan, and a skip reason dim. The text
never relies on color alone.

The meaning comes from a pure, unit-tested `frontend/src/utils/evalExplain.js` that maps
`reason`/`source`/`gaze_debug`/`diagnostics`/`intervention_debug` to the phrases above. For example:
`gaze_screen` → "looking away from screen Ns", `body_no_face` → "face not visible, body present",
`absent` → "left the desk", `tab_hidden` → "tab hidden", `calibrating` → "calibrating baseline",
`too_short` → "too short to act (<5s)", `paused_grace` → "video paused by student (grace Ns)".

### 3.3 "Distracted frames"

- The backend adds `frames_debug` to the heartbeat response: one compact entry per frame in the batch,
  up to 9, with `t`, `face`, `on_screen`, `yaw_dev`, `pitch_dev`, `sx`, `sy`. That data is already
  in `LiveWindowScorer` frames, so no extra inference is needed.
- The terminal shows a strip such as `frames ●●●○○●●●●`, with ● off-screen and ○ on-screen. Expanding a
  DISTRACTED line lists each frame in words: `+0.33s face ✓ off-screen (gaze x=0.12 y=1.31) yaw −21°`.
- **Thumbnail** (eval mode only): the client already holds the JPEGs it sent, so it keeps the frame
  nearest the decision for DISTRACTED lines and shows a 96 px thumbnail on hover. Frames stay in memory only:
  nothing extra is uploaded or stored, and everything is cleared on session stop.

### 3.4 Evaluator tools (toolbar)

- **Pause scroll** and **Clear**.
- **Mark** (key `M`): inserts a ground-truth marker line such as `[MARK] evaluator: distracted now`, so
  a reviewer can line up what they observed with what the model said.
- **Export**: download the session log as JSONL (raw responses plus marks) and CSV
  (`t, verdict, p_model, p_gaze, p_fused, source, reason, face_ratio, episode_sec, action, why, tier, mark`).
  This produces evaluation evidence for Chapter 6 without touching the DB.
- Ring buffer of 500 lines, so memory stays bounded.

### 3.5 PLAN 6 compatibility

When `evidence`/`rule` keys appear (PLAN 6 step 2), the second line adds
`evidence: gaze STRONG · head WARNING · noise normal → rule B (2 signals ≥5s)`.

## 4. Files

| File | Change |
|---|---|
| `backend/app/services/intervention_engine.py` | `last_decision` trace; `held_seconds` per episode; pause grace + tier-2 cap for user-paused |
| `backend/app/routes/session.py` | pass `content_state`/`pause_reason` to the engine instead of the blanket hold; return `intervention_debug`, `frames_debug` |
| `backend/app/schemas/session_schema.py` | optional `pause_reason` |
| `backend/app/services/ml_service.py` | per-frame `frames_debug` from the live scorer |
| `frontend/src/components/student/VideoLearningPlayer.jsx` | send `pause_reason`; neutral buddy on `ended`; mount `EvalTerminal`; StrictMode start guard |
| `frontend/src/hooks/useMonitoringSession.js` | keep a log of responses + last sent frames for the terminal; start de-dup |
| `frontend/src/components/student/EvalTerminal.jsx` | new overlay |
| `frontend/src/utils/evalExplain.js` | new reason → plain-language mapper |

## 5. Tests

- Backend (`test_intervention_engine.py`, `test_session.py`):
  - paused <10 s → `why=paused_grace`; paused ≥10 s → fires, tier ≤2; ended → `why=ended`.
  - pending prompt → `why=pending` with time left; cooldown → `cooldown_left_sec`.
  - held 20 s and then resumed → the first fire is **T1**, not T3 (regression for Bug 2).
  - every skip path sets `last_decision.why`.
  - the heartbeat response contains `intervention_debug` and `frames_debug` (≤9 entries).
- Fix the 2 pre-existing `test_noise_monitor.py` failures. They still assume the old 20 s T1 timeout from
  before the uncommitted PLAN 5 change to 6 s.
- Frontend: unit tests for `evalExplain.js`, covering every reason and why code.
- Manual check: rerun the session-158 pattern (pause the video, look away 30 s) and confirm that the terminal shows
  `paused_grace` and then `FIRED T1`. Then play the video, look away 6 s, and confirm `FIRED T1` at ~5 s, T2 on ignore,
  and so on. Export the log to `dev/test_outputs/phase7_terminal_log.jsonl`.

## 6. Order of work

1. Engine: `last_decision` trace + honest clock + pause grace, with tests (this fixes the bug).
2. Route: wire `pause_reason`, return `intervention_debug`/`frames_debug`; fix noise tests.
3. Frontend: `pause_reason`, ended-neutral buddy, StrictMode start guard.
4. `evalExplain.js` + `EvalTerminal.jsx` + export/mark.
5. Manual run + exported log.
