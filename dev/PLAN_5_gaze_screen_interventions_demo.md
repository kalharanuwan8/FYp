# PLAN 5 — Screen-mapped gaze, fast escalation, video fullscreen, demo triggers

Date: 2026-11-13 · Branch: `expert-remediation` · Python: **`venvpy312\Scripts\python.exe` only** (never `venv` / `.venv`)

## Context — what is wrong today (verified in code at `7714fa6`)

| Concern | Current state |
|---|---|
| Live model crashes | `[MLService] Live scoring error: 'Model6SklearnWrapper' object has no attribute '_cal'` on every heartbeat. `models/outputs/checkpoints/model6_v3/model.pkl` was pickled with an older `Model6SklearnWrapper` (no `_cal`); unpickling skips `__init__`, so `predict_proba` (`models/src/model6_natural/wrapper.py:86`) raises. Live verdicts fall back / are lost. |
| Gaze off screen not marked distracted | `_on_screen` (`models/src/features/windows.py:32-39`) = head yaw/pitch < 18° from baseline and iris L1 dev < 0.35 from a fixed 0.5 centre. No knowledge of the screen at all. Normal look-aways count as on-screen. Calibration (`CalibrationOverlay.jsx`) only locks a head-pose baseline; `live.py:110` still has `if self._calibrating or True:`. |
| Unanswered T1 → T2 | Not done. `PROMPT_TIMEOUT_SEC = 20.0`, `DEFAULT_COOLDOWN_SEC = 30.0` (`backend/app/services/intervention_engine.py:43-45`) → T2 ≈ 50 s after T1. Timeouts never persisted (`set_timeout_callback` never wired). |
| Video fullscreen | Not implemented (no `requestFullscreen` anywhere in `frontend/src`). |
| Manual demo triggers in video | `DemoPanel` exists in `VideoLearningPlayer.jsx:320` but is hidden behind Ctrl+Shift+D, and `force_intervention` still respects pending/cooldown → 409s during a demo. |

## Decisions (confirmed with user)
- Screen area: **5-point look calibration** (4 corners + centre, ~2 s per dot).
- Off-screen gaze for **~2 s** ⇒ DISTRACTED. Every off-screen frame is marked and weighted as distracted.
- Unanswered **T1 after 6 s ⇒ T2 immediately**; T2→T3 and T3→T4 spaced **20 s**.
- Demo sidebar: **visible** (behind a `DEMO_MODE` flag), **bypasses** pending/cooldown.
- Keep the trained model6 v3 (no retraining); add a screen-gaze layer on top.

---

## Step 0 — Fix the `_cal` crash (do first; blocks everything)
File: `models/src/model6_natural/wrapper.py`
- Add `__setstate__` to `Model6SklearnWrapper` that sets defaults for attributes added after the pack was pickled (`_cal=None`, `_model=None`, `_device=cpu`, `hidden=64`), then `self.__dict__.update(state)`.
- In `predict_proba` use `getattr(self, "_cal", None)` defensively.
- Check `PlattCalibratedProba` / any other pickled class in the pack for the same drift.
- Test `backend/tests/test_ml_hardening.py`: load the real `model6_v3/model.pkl`, call `predict_proba` on a 14-feature zero vector → shape (1,2), no exception. Plus a unit test that a wrapper pickled without `_cal` still predicts.

## Step 1 — Screen-mapped gaze (the main fix)

### 1a. Frontend: identify screen + 5-point calibration
- New `frontend/src/components/student/ScreenCalibrationOverlay.jsx` (replaces `CalibrationOverlay` usage in `VideoLearningPlayer.jsx` and `SubjectDetail.jsx`):
  1. Read device display: `window.screen.width/height`, `window.innerWidth/innerHeight`, `devicePixelRatio`, `screen.orientation`. Enter fullscreen for the calibration so the content area == the screen.
  2. Show 5 dots in order: centre, top-left, top-right, bottom-right, bottom-left (inset 5% from edges), each ~2 s with a shrinking-ring animation ("look at the star").
  3. While a dot is shown (ignoring the first 600 ms for eye travel), tag captured frames with `calib_target: {x, y}` in normalized screen coords (0..1).
  4. On finish show result (“Screen mapped ✓” / “Couldn’t see your eyes – retry”) from the backend response.
- `frontend/src/hooks/useMonitoringSession.js`:
  - capture 640×480 @ 15 fps (currently 320×240), frame every 333 ms, `MAX_BUFFERED_FRAMES` 9;
  - add `calib_target` per frame and a `screen` object `{w, h, inner_w, inner_h, dpr}` on the heartbeat;
  - expose `gazeDebug` from heartbeat response.
- `backend/app/schemas/session_schema.py`: allow optional `calib_target` per frame, `screen` object, `calibration_phase: "start"|"collect"|"finish"`; raise `MAX_FRAMES_PER_HEARTBEAT` to 9 and check `MAX_IMAGE_B64_CHARS` for 640-wide JPEG q≈0.7.

### 1b. Backend: fit a gaze → screen mapping
- New `models/src/features/screen_gaze.py`:
  - `ScreenGazeMapper.fit(samples)` — samples are per-frame `(yaw, pitch, iris_x, iris_y) → (sx, sy)`. Use the per-dot **median** (robust to blinks). Fit two small ridge regressions:
    `sx = a0 + a1·yaw + a2·iris_x (+ a3·yaw·iris_x)`, `sy = b0 + b1·pitch + b2·iris_y`.
    With 5 points use the linear form (3 params each); require ≥4 valid dots and a fit residual < 0.15 screen units, else `ok=False`.
  - `predict(frame) → (sx, sy)`; `is_on_screen(frame, margin=0.12)` ⇒ `-m ≤ sx ≤ 1+m and -m ≤ sy ≤ 1+m`.
  - Blink frames (eye-blink blendshape > 0.5, from `face_pose.py`) → *neutral* (skip, not off-screen). Per-frame 3-sample median smoothing on iris.
  - No face but body present ⇒ off-screen (child looked away/down hard).
- `models/src/features/live.py` (`LiveWindowScorer`):
  - collect calibration samples while `calib_target` present; on `finish` fit the mapper and lock the head baseline from the centre dot (remove the `or True` at line 110).
  - **Fallback** if the fit fails or calibration is skipped: baseline-centred rule — iris baseline from the first 10 face frames, off-screen if |Δiris_x| > 0.08 or |Δiris_y| > 0.10 or |Δyaw| > 12° or |Δpitch| > 12° (env-tunable).
  - Keep slow EMA re-baseline for head only, and only while gaze is on-screen.

### 1c. Every off-screen frame is weighted as distracted
- `models/src/features/windows.py`: add optional `on_screen_fn` parameter to `aggregate_window` (default = existing `_on_screen`, so training/thesis feature extraction is unchanged). The live scorer passes the screen mapper, so the model's `on_screen_ratio`, `off_screen_dwell_sec`, `glance_count` all reflect the real screen box.
- `backend/app/services/ml_service.py` `_decide_live` (~line 1105):
  - per frame: `frame_label = DISTRACTED if off-screen`.
  - **gaze dwell rule**: continuous off-screen dwell ≥ **2.0 s** (env `ML_GAZE_OFFSCREEN_SEC`) ⇒ `p_gaze = 0.9`; off-ratio over the last 3 s scales `p_gaze` below that.
  - fused `p = max(p_model, p_gaze)`; `decision_source = "gaze_screen"` when the gaze rule wins.
  - gaze-driven DISTRACTED bypasses the 3 s hysteresis enter hold (the 2 s dwell *is* the hold); exit still needs on-screen ≥ 2 s.
  - raise the hysteresis timer-reset gap 4.0 → 6.0 s; live window 5 s → 3 s.
  - return `gaze_debug {sx, sy, on_screen, off_dwell_sec, p_model, p_gaze, source, calibrated}` in the heartbeat response.
- `backend/app/routes/session.py`: forward `calib_target`/`screen`/`calibration_phase` to the scorer; heartbeat returns calibration status. One-heartbeat grace before an UNKNOWN closes an open distraction episode (`session.py:240-250`).

Target: look off-screen (eyes or head) for ~2 s ⇒ DISTRACTED within ≤ 1 heartbeat after the dwell (≈ 2–4 s total).

## Step 2 — Unanswered intervention ⇒ next tier immediately
Files: `backend/app/services/intervention_engine.py`, `backend/app/routes/session.py`, `frontend/src/components/intervention/InterventionOverlay.jsx`
- Per-tier prompt timeouts: **T1 = 6 s**, T2/T3 = 20 s, breaks no deadline (`TIER_TIMEOUT_SEC = {1: 6, 2: 20, 3: 20}`).
- `tick()` returns the records it expired. In `send_heartbeat`: if an expired record was **T1 ignored**, immediately call `force_intervention(2, source="escalation")` in the same request — no cooldown, no fresh DISTRACTED verdict needed (ignored ⇒ distracted).
- Cooldown after resolution: **20 s** (`DEFAULT_COOLDOWN_SEC` 30→20; seed `intervention_min_cooldown_seconds` "20" in `backend/app/__init__.py:407` and update the existing Postgres row at startup if still "30"). Escalation T2→T3→T4 continues on the normal path with ignored ⇒ `last_tier+1`.
- Heartbeat interval is 2 s, so T2 appears 6–8 s after an unanswered T1.
- Wire `set_timeout_callback` so timeouts write `InterventionLog.outcome="ignored"`, `user_response="timeout"`.
- Fix `session.py:815`: pass `intervention_id` to `record_outcome` so a late click on an expired T1 can't resolve the new T2 (stale click ⇒ 200 no-op).
- Frontend: when a new intervention arrives, it **replaces** the one on screen (T1 banner disappears, T2 pacing pause shows and pauses video).
- Tests: update `test_intervention_engine.py`, `test_intervention_escalation.py`, `test_intervention_v4.py` (T1 deadline 6, cooldown 20) + new test: T1 fired, no answer, heartbeat at +6 s ⇒ response contains a T2.

## Step 3 — Video fullscreen
- New `frontend/src/hooks/useFullscreen.js` (`requestFullscreen` / `exitFullscreen`, `fullscreenchange` listener, Esc sync, webkit prefix).
- `VideoLearningPlayer.jsx`: fullscreen button (+ `F` key) in the control bar. Fullscreen targets a **video stage container** holding only: the `<video>`, intervention overlays, a minimal auto-hiding control bar (play/pause, mute, exit fullscreen, camera on/off), and the demo sidebar toggle. Everything else (header, module info, side content) is hidden. Native `<video>` fullscreen is *not* used because it would hide interventions.
- Camera preview: small toggleable thumbnail inside the stage (hidden by default in fullscreen; camera keeps running when hidden).
- Interventions and the demo sidebar render inside the fullscreen element (portal target = stage), otherwise they'd be invisible in fullscreen.

## Step 4 — Manual demo triggers in the video player
- Backend: `DEMO_MODE` config (env, default false) + `demo_mode` exposed to the client (`GET /api/session/demo-config`). `POST /api/session/<id>/trigger-intervention` accepts `force: true` (honoured only when `DEMO_MODE`): resolves any pending prompt as `ended` (source `demo`, not counted as ignored) and bypasses cooldown/tier-enable checks via `force_intervention(..., bypass=True)`.
- Frontend: turn `DemoPanel.jsx` into a **right-edge slide-out sidebar** with a visible "Demo" tab (Ctrl+Shift+D still works), shown when `demo_mode` is true, in both `VideoLearningPlayer.jsx` (incl. fullscreen) and the `SubjectDetail.jsx` focus view:
  - Buttons: T1 Ambient cue · T2 Pacing pause · T3 Milestone quiz · T4 Content pacing · T4 Break · Noise notice.
  - "Simulate ignore" toggle (lets the audience watch T1 → T2 auto-escalation).
  - Live readout from `gaze_debug`: on/off screen dot on a mini screen rectangle, off-screen dwell, p_model, p_gaze, verdict.
  - Error line for any failure (add `try/catch` in `SubjectDetail.jsx:387`).
- Delete unused `ManualInterventionPanel.jsx`.

## Step 5 — Carry-over from the earlier request (still not done)
- Grades: script `backend/scripts/cleanup_grades.py` (`--dry-run` default, `--apply`): ensure Grade 1–12, reassign subjects/students on any other grade to "Grade 1", delete other grade rows. `GET /api/courses/grade-levels` filters to `Grade 1..12`, ordered numerically.
- Stop session: in `SubjectDetail.jsx:632-639`, when a session is active for the module, the "Start focus session" button becomes a red **"Stop session"** button in the same place (calls `handleStopSession`).

---

## Verification
1. `venvpy312\Scripts\python.exe -m pytest backend/tests -q` — all green (incl. `_cal` pack-load test, screen-mapper unit tests with synthetic calibration points, gaze dwell ⇒ DISTRACTED test, T1 6 s ⇒ T2 heartbeat test, demo force bypass test, grade filter test).
2. `venvpy312\Scripts\python.exe -m pytest models/tests -q` — training feature path unchanged (`_on_screen` default).
3. `cd frontend; npm run build`.
4. Manual run with `DEMO_MODE=true`:
   - Backend log shows **no** `Live scoring error`.
   - Start a video → 5-dot calibration → "Screen mapped ✓".
   - Demo sidebar readout: dot follows gaze inside the screen box; look at the wall/phone for 2 s ⇒ verdict DISTRACTED (`source=gaze_screen`); look back ⇒ FOCUSED after ~2 s.
   - Leave T1 unanswered ⇒ T2 pacing pause within 6–8 s; leave T2 ⇒ T3 ≥ 20 s later.
   - Demo buttons fire instantly even while another intervention is open.
   - Fullscreen: only the video + overlays visible; interventions and demo sidebar still appear; Esc exits.
   - `cleanup_grades.py --dry-run` then `--apply`; grade dropdown shows Grade 1–12 only.

## Order of work
Step 0 → Step 2 (small, high value) → Step 1 → Step 4 → Step 3 → Step 5 → verification.
