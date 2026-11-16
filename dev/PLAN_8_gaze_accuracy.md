# PLAN 8: Make eye-gaze distraction detection actually work (and fire T1 at 3 s)

The first step of implementation copies this file to `dev/PLAN_8_gaze_accuracy.md`, as you asked.

## Context

After the PLAN 7 fixes, interventions do fire. Session 159 logged 11 T1/T2 prompts. But **eye-only distractions
are still missed**, even though calibration showed the success screen:

- eyes only, left or right (head still)
- eyes only, up
- looking **just past** the left or right edge ("near the screen but not on it")

The DB shows why the prompts that did fire happened: 64 of 94 DISTRACTED beats in session 159 were `body_no_face`
(the face was lost). Only 30 came from the gaze path, so gaze contributes little.

Goals:
1. Eye-only off-screen gaze in any direction, including just past the edge, is detected.
2. The first intervention (T1) appears about **3 s** after looking away, and that number is a single setting.
3. A guided **gaze self-test** shows you, direction by direction, whether detection works. It shows pass/fail
   only, with no thesis numbers.

## Root causes (verified in code)

| # | Defect | Where | Effect |
|---|---|---|---|
| 1 | Vertical eye position is measured **relative to the eyelids**: `vy = (iris.y - top) / (bot - top)`. The lids move with the eye, so looking up or down barely changes it. | `models/src/features/face_pose.py::_iris_ratio` | "eyes up" and "eyes down" are not seen |
| 2 | Looking down raises `eyeBlink`. Frames with blink >0.5 **copy the previous (on-screen) prediction**. | `screen_gaze.py::observe/predict`, `live.py::_fallback_on_screen` | looking down at a phone reads as "on screen" |
| 3 | The calibration says "keep your head still", but the mapper still **fits a head-yaw/pitch weight** from 5 dots where the head hardly moves. That weight is noise and can have the wrong sign. | `screen_gaze.py::fit` (ridge on `[1, yaw, iris_x]`) | edges and head movement map unpredictably |
| 4 | The on-screen box is enlarged by `DEFAULT_MARGIN = 0.12`, i.e. 12% of the screen beyond each edge. | `screen_gaze.py::is_on_screen` | "just past the edge" counts as on screen |
| 5 | Horizontal iris ratio only: about a ±0.15 range across the screen, with noise of about 0.03. | `_iris_ratio` | weak left/right resolution |
| 6 | Timing: gaze must stay off for 2 s to enter DISTRACTED. The episode starts at that heartbeat, and T1 needs an episode of at least 5 s, on a 2 s heartbeat. | `ml_service.gaze_offscreen_sec`, `intervention_engine.distraction_level_from_duration`, `VideoLearningPlayer intervalMs: 2000` | T1 arrives about 7–9 s after looking away |

## Approach

### A. Better eye features (`models/src/features/face_pose.py`)
- Add MediaPipe **eye-look blendshapes**, which are already computed (`output_face_blendshapes=True`). Reuse `_blendshape_score`:
  - `look_h = mean(eyeLookOutLeft, eyeLookInRight) - mean(eyeLookInLeft, eyeLookOutRight)`
  - `look_v = mean(eyeLookUpLeft, eyeLookUpRight) - mean(eyeLookDownLeft, eyeLookDownRight)`
- Add `look_h`, `look_v` and `look_down` to `FrameFeatures`, each with a default of 0.0 so existing callers and tests don't break.
- Fix the vertical iris measure: take `iris.y` relative to the **eye-corner midline** (corners don't move with the lids) and
  normalise by eye width. Keep the field name `iris_y`.
- Keep the old fields, because the model6 training/cache code reads them.

### B. Blink vs. looking down (`screen_gaze.py`, `live.py`)
- `is_blink(f) = blink > 0.5 and look_down < 0.4`. Looking down with lowered lids is **not** a blink, so it is mapped
  like any other gaze.
- Use this helper everywhere `BLINK_THRESHOLD` gates gaze: `observe`, `predict`, `_fallback_on_screen`, and the iris baseline.

### C. A screen mapper that is right about the head (`screen_gaze.py`, `ScreenCalibrationOverlay.jsx`, `live.py`)
- Add a short **head phase** to the calibration, about 4 s after the 5 stars: "keep your eyes on the star and slowly
  turn your head left and right, then nod". These frames are tagged with the centre target. Gaze stays fixed while the
  head moves, which teaches the model how eye position compensates for head angle, with the correct sign.
- Fit on **per-frame samples** from both phases, with the 2 most extreme frames per dot trimmed, instead of 5 per-dot
  medians. Design: `sx ~ [1, yaw, iris_x, look_h]` and `sy ~ [1, pitch, iris_y, look_v]`. Keep the ridge regularisation.
  The residual is still checked on per-dot medians (`MAX_RESIDUAL` unchanged).
- If the head phase is missing (an old client), freeze the head weight to 0 and rely on the eye terms plus the existing
  baseline head-deviation check: off-screen when |yaw−yaw0| > 12° or |pitch−pitch0| > 12°, reusing
  `fb_yaw_deg`/`fb_pitch_deg`.
- `DEFAULT_MARGIN` 0.12 → **0.03**, overridable with `ML_GAZE_MARGIN`.

### D. T1 at 3 s from a single number
- New setting `INTERVENTION_T1_SEC = 3.0` in `backend/app/config.py`, overridable with the env var `INTERVENTION_T1_SEC`.
  It's the **only** number to change.
- `ml_service.gaze_offscreen_sec` defaults to `min(2.0, INTERVENTION_T1_SEC)`, so the verdict always enters before T1 is due.
- The gaze-driven episode is **backdated to when the eyes left the screen**. `ml_service` returns
  `distracted_since_sec = off_dwell_sec` (meta) when `source == gaze_screen`. `upsert_distraction_episode` in
  `routes/session.py` sets `started_at = now_dt - distracted_since_sec` when it opens a new episode.
- `distraction_level_from_duration` in `intervention_engine.py` reads its level-1 threshold from the setting
  (`< T1 → 0`). The T2/T3/T4 bands (10/20/40 s) are unchanged.
- Heartbeat interval 2 s → **1 s** (`VideoLearningPlayer.jsx` `intervalMs: 1000`). The capture rate stays at ~3 fps, so
  the server does the same work in smaller batches. Expected T1 is 3–4 s after looking away.
- The PLAN 6 evidence tracker stays **unwired**. Its 5 s two-signal rule contradicts the 3 s requirement. Note this in PLAN 6.

### E. Guided gaze self-test (frontend only; no new backend endpoint)
- New `frontend/src/components/student/GazeSelfTest.jsx`. It opens from the success screen of
  `ScreenCalibrationOverlay` ("Test it") and from the eval terminal toolbar (`gaze test` button).
- It runs 6 steps of 4 s each, head still: look at the centre, then just past the LEFT edge, just past the RIGHT edge,
  ABOVE the screen, DOWN at the desk/phone, and back at the centre.
- Each step reads the `frames_debug[].on_screen` already returned on every heartbeat (PLAN 7). A step **passes** when
  most frames in its last 2 s match the expected state.
- The result is a simple ✓/✗ per direction, with "Recalibrate" and "Run again" buttons. There are no accuracy numbers.
  Frames go through the normal heartbeat and nothing extra is stored.
- The hook exposes the latest response through a subscriber, `onHeartbeat`. That's an additive option on
  `useMonitoringSession`, beside `onIntervention`.

## Files

| File | Change |
|---|---|
| `models/src/features/face_pose.py` | `look_h/look_v/look_down`; corner-midline `iris_y` |
| `models/src/features/screen_gaze.py` | `is_blink`; per-frame trimmed fit with eye-look terms; margin 0.03 (env) |
| `models/src/features/live.py` | head-phase samples; blink helper in fallback/baseline; `frame_debug` adds `look_h/look_v` |
| `backend/app/services/ml_service.py` | `gaze_offscreen_sec` derived from T1; `distracted_since_sec` in meta |
| `backend/app/config.py` | `INTERVENTION_T1_SEC = 3.0` (env) |
| `backend/app/services/intervention_engine.py` | level-1 band from the setting |
| `backend/app/routes/session.py` | backdate a new gaze episode; pass T1 to the engine |
| `frontend/src/components/student/ScreenCalibrationOverlay.jsx` | head phase after the 5 stars; "Test it" button |
| `frontend/src/components/student/GazeSelfTest.jsx` | new |
| `frontend/src/hooks/useMonitoringSession.js` | `onHeartbeat` option |
| `frontend/src/components/student/VideoLearningPlayer.jsx` | `intervalMs: 1000`; mount self-test |
| `frontend/src/components/student/EvalTerminal.jsx` | `gaze test` button; show `look_h/look_v` in the frame lines |

## Verification

1. **Unit tests**
   - `models/tests/test_screen_gaze.py`, synthetic frames:
     - eyes-only left/right/up/down past the edge → off-screen; just inside the edge → on-screen
     - a looking-down frame with high blink and high look_down → off-screen, not "copy previous"
     - a real blink → neutral
     - a head turn with the eyes compensating (gaze fixed) → on-screen
     - margin env override honoured
   - `backend/tests/test_intervention_plan7.py` + a new `test_gaze_timing.py`:
     - with `INTERVENTION_T1_SEC=3`, a gaze episode backdated 2 s fires T1 on the next beat (episode ≥3 s)
     - changing the setting to 6 moves T1 accordingly
     - the T2/T3 bands are unchanged
   - Existing suites stay green: `pytest backend/tests models/tests`.
2. **Build/lint:** `npx eslint` on the changed files; `npx vite build`.
3. **Manual run** (your webcam, `?eval=1`):
   - Calibrate, including the head phase, then run the gaze self-test. All 6 steps should be ✓.
   - Play the lesson and move only your eyes just past the left edge. The eval terminal should show
     `[●●●] eyes off screen` and then `FIRED T1 ambient cue` about 3–4 s after the eyes leave.
   - Repeat for up and down (phone).
   - Set `INTERVENTION_T1_SEC=5`, restart, and confirm T1 now arrives at about 5–6 s.

## Out of scope
- Retraining model6. Its window features keep their names; only the on-screen decision feeding them improves.
- Wiring PLAN 6.
- Thesis numbers.
