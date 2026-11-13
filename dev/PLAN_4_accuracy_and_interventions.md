# PLAN 4: system audit and fixes for detection accuracy and intervention triggering (72 h)

## Context
A fresh audit of branch `expert-remediation` (3 parallel audits: live detection, intervention triggering, model6 training) found two root problems:

1. **Detection is not trustworthy yet.**
   - The deployed `models/outputs/checkpoints/model6_v3/model.pkl` was trained on **rule labels (circular), 3 subjects (S01–S03)**, and its threshold/hysteresis fell back to the defaults (`inner_f1 = 0`).
   - Replayed on cached frames, it flags 0–7% of windows in the S02/S03/S05 distracted clips, and raises 0.6–1.6 false alarms/min on natural clips.
   - The serving path also has false-positive leaks: partial face dropouts read as "off-screen"; `body_no_face` returns DISTRACTED and skips hysteresis; hysteresis timers survive long gaps; the baseline is whatever the first 15 s happen to be; frames are squashed to 320×240.
   - It also misses things: tab or app switching and leaving the desk are never counted as distracted.
2. **Intervention triggering is logically broken.**
   - "Ignored" only exists if the child clicks Skip or Dismiss, so a child who ignores prompts never escalates.
   - One FOCUSED verdict wipes escalation memory and the pending lock while the prompt is still on screen.
   - One UNKNOWN restarts the episode, so the gentle cue repeats about every 8 s.
   - Outcomes aren't matched to intervention ids, and noise outcomes corrupt visual escalation.
   - The cooldown counts from when the prompt fires, which causes back-to-back 60 s breaks.
   - Rule-mode and no-face verdicts escalate all the way to breaks.
   - The docs (`SYSTEM.md`, `DOCTOR_REVIEW_BRIEF.md`) don't match the code.

The frame cache for all 21 clips (S01–S07 × focused/distracted/natural) is **already complete** (`models/data/processed/model6_natural/frames/`). No annotation files exist yet.

**User decisions (confirmed):**
- **Annotation:** mark *distraction spans* in every clip. In distracted clips, unmarked time = **unlabelled (dropped)**. In focused and natural clips, unmarked time = focused. Natural clips are used for evaluation only.
- **Intervention timeout:** an unanswered prompt becomes "ignored" after **20 s**. Breaks are exempt.
- **Browser signals:**
  - Tab hidden ≥3 s → distracted.
  - Window blur ≥5 s → distracted.
  - Video deliberately paused → hold the episode clock.
- **Calibration:** an explicit **10 s calibration screen** at session start, plus a slow rolling re-baseline from confidently-focused frames.

Carried over from PLAN_3: `engagement = 1 − P(distracted)`. M1/M2/M3 are not retrained. Nested LOSO. Commits only after user approval.

---

## Phase A: checkpoint + annotation tool (hours 0–4). Unblocks the user.
1. Commit checkpoint of the current uncommitted remediation work (after user OK). Phase 0 tests already pass (see `dev/test_outputs/phase0_scratchpad.md`).
2. Fix `models/scripts/annotate_clip.py`:
   - Undo the last span with `U`, and delete the span under the cursor with `X`.
   - Reload existing spans without duplicating them.
   - No exit at the end of the video: clamp the seek to `n_frames − 1`.
   - Show the correct timestamp.
   - Seek by time (`CAP_PROP_POS_MSEC`) for .MOV/VFR files.
   - Only the `D` key is needed under the new protocol; keep `F` for corrections.
   - Write `<clip>_labels.csv` (`start_sec,end_sec,label`) plus a `protocol_version=v4_distraction_spans` header comment.
3. **User annotates** (about 1.5–2 h, in parallel with Phases B–C). Definition, printed by the tool: off-screen attention ≥2 s (phone, looking away, talking, absent, drowsy, eyes off the lesson). Glances <2 s are not distraction. Mark every such span in all 21 clips.

## Phase B: training-side fixes (hours 4–14)
**Labels** (`models/src/model6_natural/extract.py`):
- New label policy `distraction_spans`:
  - focused/natural: default 0, spans → 1.
  - distracted: default **None**, spans → 1. Unmarked windows are dropped, except those inside a focused span explicitly marked with `F`.
  - Natural rows: `eval_only = 1`.
- Lower window label coverage from 0.8 to **0.6** (`extract.py:41`), so 3–4 s spans yield positives.
- Natural clips: use a **per-clip live-style baseline** (first 30 face frames of that clip, via the same function as `live.py`) to match serving. Keep the focused-clip baseline for the training clips. Add a flag `--baseline live|focused`.
- Fix the default `--labels`, and stop overwriting the `condition` column.

**Features** (`models/src/features/windows.py`, shared with live via `models/src/features/live.py`, so no skew):
- `hand_to_face`: count a frame as "near" only when `body_present` (the cached column exists, so no re-cache needed).
- Replace absolute `head_roll_mean` with `head_roll_dev` (relative to baseline roll; add roll to `compute_pose_baseline`).
- `on_screen_ratio`, `off_screen_dwell_sec`, `gaze_dev_*`: compute over **face-present frames only**. Missing-face fraction stays in `face_present_ratio`, so face loss isn't disguised as off-screen.
- Dwell: compute from real timestamps, not `window_sec / len(win)`.
- Ablation candidates, decided by data: `blink_rate`, `perclos`, `talking_score`, `body_motion_energy`.
- Update `test_feature_parity.py` expectations to match.

**Trainer** (`models/src/model6_natural/train.py`):
- Pooled summary uses `_fit_mask` only. Report natural-clip metrics separately: window F1/PR-AUC, **span detection rate** (share of annotated spans hit by ≥1 positive), and **FA/min** (onsets that don't overlap a positive span ±2 s, counted on the full sequence).
- Add `--exclude-subjects` (S05 camera confound run), feature-group ablations, and a reliability plot.
- Per-subject sample weighting (S06 has 2× the windows). Platt calibration fit on the inner out-of-fold predictions.
- **Tune threshold and hysteresis in the inner loop by replaying at the live cadence** (2 s heartbeat updates). Objective: max inner F1 subject to natural-style FA ≤ 0.5/min, falling back to the best-F1 configuration if none meets the constraint, so the defaults never silently win.
- Deterministic runs on `--device cpu` (the dataset is small). `torch.use_deterministic_algorithms(True)`.
- `deploy()`: keep the LR-if-better rule. Pack `kind` = `model6_mlp` or `model6_logreg`, both loaded by the backend (Phase C).
- Baselines: majority, `distraction_proxy` rule, logistic regression. Bootstrap 95% CI across 7 subjects.

**Tests** (`models/tests`): the human-label extract path (span policy, dropped unlabelled windows, coverage), the `hand_to_face` default, FA/min counting, pooled-metric masking, and a deploy-pack round trip.

Run order once labels arrive (about 3 h CPU): extract with `--labels human --from-cache` → train → full run, S05-excluded run, ablations → deploy to `models/outputs/checkpoints/model6_v4/`.

## Phase C: live detection fixes (hours 6–24, parallel with B)
**Backend** `backend/app/services/ml_service.py`:
- `_has_v3_pack` accepts `model6_mlp` and `model6_logreg`. Load the newest pack (v4 → v3). **Log loudly and expose `/health` → `ml_mode`** when falling back to rule mode.
- Face gate: face_present_ratio < **0.6** → UNKNOWN `low_face`, instead of handing the window to the model.
- `body_no_face`: route it through hysteresis as p = 0.7 (no instant DISTRACTED). After 10 s or more without a body, mark it **away** (DISTRACTED, source=`absent`) through hysteresis.
- Hysteresis: reset `high_t0` / `low_t0` when the gap since the last scored window exceeds 2× the heartbeat interval, or when the window is gated UNKNOWN.
- Score **every 1 s hop** inside each heartbeat batch, not only the last window, to match training cadence. Return `window_end_ms` with the verdict.
- Thread safety:
  - `clear_session` and `reap_idle_sessions` take the session lock.
  - Initialise the model wrapper eagerly under a lock.
  - Use a lock for the hysteresis dicts.
- Reset the scorer when client timestamps go backwards.
- Delete the dead legacy M1/M2/M4/M5 path: `_score_window`, Haar cascades, constant `gaze_probs`, `eng_prob = 0.5`, the 0.85 constant. Keep `predict_frame_image` → `predict_frames`.
- Add `engagement_score = 1 − p` (from PLAN_3).

**Calibration + baseline** (`models/src/features/live.py`):
- The scorer accepts `calibration_frames`. The baseline is locked from the calibration phase.
- A rolling re-baseline (EMA, α small) uses only frames from windows with p < 0.2 and face present, with drift clamped to ±10°.
- Verdicts are UNKNOWN `calibrating` until the baseline is locked.

**Browser signals** (`backend/app/schemas/session_schema.py` and the heartbeat route):
- New heartbeat fields: `page_visible: bool`, `window_focused: bool`, `hidden_ms`, `blurred_ms` (the continuous duration so far), `content_state: playing|paused|ended|none`, `calibrating: bool`.
- `hidden_ms ≥ 3000` or `blurred_ms ≥ 5000` → DISTRACTED, source=`tab`/`blur`. This overrides the camera, and is logged separately in analytics.

**Frontend** `frontend/src/hooks/useMonitoringSession.js`:
- Canvas sized from `video.videoWidth/Height` (aspect kept), width 640, JPEG 0.8.
- `visibilitychange` + `focus`/`blur` listeners, durations tracked and sent.
- While hidden, send a lightweight heartbeat even with no frames (throttling-tolerant: the server uses `hidden_ms`, not cadence).
- Keep `loopStartRef` per session, not per loop call.
- New `CalibrationOverlay` component: 10 s "look at the lesson", progress ring, sends `calibrating: true` frames, retry if the face is not found.
- Video components report `content_state`.

**Coverage** (`backend/app/services/observation_coverage.py`): use `window_end_ms` anchored to session start instead of server receipt time.

## Phase D: intervention triggering fixes (hours 14–34)
**`backend/app/services/intervention_engine.py`:**
- **Pending state = {id, tier, source, fired_at, deadline}.**
  - Deadline = fired_at + 20 s for tiers 1–3 and the noise notice; breaks are exempt.
  - On each heartbeat, an expired pending prompt is recorded as `ignored` with `user_response = "timeout"` (DB log updated).
- `record_outcome(outcome, intervention_id)` applies the outcome only if the id matches the pending one, ignores duplicates, and rejects answers on ended sessions (route returns 409).
- Noise source is fully isolated: noise outcomes never touch `last_tier` / `last_outcome`.
- **The cooldown starts at resolution** (answer, timeout or break end), not at fire time. A single 30 s cooldown applies to **all tiers, including tier 1**, which then fires once per episode and at most once per 30 s.
- Escalation memory reset requires **sustained FOCUSED ≥ 10 s**, and never while a prompt is pending.
- **Confidence gating:** episodes driven by `rule`, `body_no_face` or `absent` sources are capped at tier 2. Tab/blur sources may escalate. Tiers 3–4 require model-derived DISTRACTED. No prompts while recent coverage (last 30 s) is below 50%.
- Episode clock starts at the hysteresis `high_t0` (true look-away time), not at the DISTRACTED verdict.
- Remove the per-session lock-free dict: `SESSION_ENGINES` gets a `threading.Lock` per session. Re-read cooldown settings on every evaluation. Remove the unused `intervention_max_cooldown_seconds`, or wire it in as the cap.

**`backend/app/routes/session.py` (episodes):**
- An UNKNOWN run of up to 5 s keeps the episode open (paused, not counted). Close it only after a longer UNKNOWN run.
- `content_state = paused` (user-initiated) **holds** the episode clock. `ended` / `none` also hold it.
- While a pausing prompt or break is open, suspend episode accounting. Close the episode when the break ends.

**Socket.IO path:** the frontend never uses `backend/app/socket_events/telemetry.py`. Refactor it to call the same shared `process_heartbeat()` as REST (one code path, noise monitor included), with one socket test, or delete it if refactoring breaks other tests.

**Frontend:**
- `SubjectDetail.jsx`, `VideoLearningPlayer.jsx`, `QuizAttempt.jsx`: ignore an incoming intervention while one is open (the server won't send one anyway, but guard it).
- Null-id guard for the local break.
- Pace reduction is applied only after the child accepts, and is reverted at session end. It is skipped for document sessions.
- Resume the video only if it was playing before the prompt.
- The local 18-minute break is logged through the engine and uses `>=` elapsed rather than `%`.
- Add `self_report` to `InterventionResponseSchema` and persist it.

**Docs:** regenerate the timing tables in `SYSTEM.md`, `intervention_review/DOCTOR_REVIEW_BRIEF.md` and `INTERVENTION_EVIDENCE_TABLE.md` from an engine `_simulate` script output, so they can't drift. Fix the 3 s vs 5 s gap text.

**Tests** (new `backend/tests/test_intervention_v4.py`), one per audit scenario:
- Timeout → ignored → escalation.
- Stale or mismatched id.
- Noise outcome isolation.
- FOCUSED blip during a pending prompt.
- UNKNOWN mid-episode with no repeated cue.
- Break → no immediate repeat break.
- Rule/no-face capped at tier 2.
- Paused video holds the clock.
- Tab hidden → distracted.
- An end-to-end REST heartbeat sequence asserting time-to-tier: cue ≈5 s after look-away, pacing after cue resolution + cooldown, and so on.
- Concurrency smoke test (2 threads hammering heartbeat + response).

Update the expectations in `test_intervention_escalation.py`.

## Phase E: integration, replay benchmark, live test (hours 34–50)
- **New `evaluation/thesis_numbers/replay_live_pipeline.py`:**
  - Replays the cached frame CSVs (and, where possible, the raw clips through `predict_frames`) at 2 s heartbeats through the **actual backend `_decide_live` + intervention engine**.
  - Reports, per subject, against the annotated spans: detection rate, FA/min, latency from look-away to DISTRACTED, and prompts per 10 min.
  - Runs old pack vs new pack side by side. This is the headline before/after evidence.
- Real-clip parity test: `MODEL6_PARITY_CLIP=<P1 clip> pytest backend/tests/test_feature_parity.py`.
- Full suite: `venvpy312\Scripts\python.exe -m pytest backend/tests models/tests`. Run MediaPipe-heavy files on their own; don't run them alongside caching (known deadlock).
- `npx vite build`.
- Latency: `evaluation/thesis_numbers/run_heartbeat_latency.py`, CPU + CUDA, median and p95 (1 s hop scoring adds work, so check p95 < 1 s).
- **Live self-test with the user (about 40 min)**, using `live_webcam_selftest.py` phases plus new phases for calibration, tab switch, phone use facing the camera, leaving the desk, and ignoring prompts. Record `ml_mode`, sources and the tier timeline.

## Phase F: write-up (hours 50–64) and buffer (64–72)
- `evaluation/thesis_numbers/REPORT_10_REMEDIATION.md`: issues found (from this audit), fixes, the new nested-LOSO numbers with CIs, baselines, ablations, natural-clip FA/min, replay benchmark before/after, latency, and the live test.
- `ERRATA_VIVA.md`: as in PLAN_3, plus the withdrawn rule-label v3 pack and the corrected intervention timings.
- `SYSTEM.md`: the v4 pipeline, calibration, browser signals, and the new intervention state machine.
- Overwrite `dev/PLAN_3_model_training_v3.md` with this plan as `dev/PLAN_4_accuracy_and_interventions.md`.
- Buffer: re-annotation fixes, the S05-excluded rerun, final commit (after user approval).

**Cut order if behind:** κ (second annotator) → reliability plot → ablations → socket refactor (delete instead) → coverage time-anchoring.
**Never cut:** human span labels, nested LOSO + baselines, the inner-loop hysteresis tuning, the intervention timeout/id/cooldown fixes, the face gate and hysteresis reset, the replay benchmark, ERRATA.

## User actions
1. Approve the Phase A checkpoint commit.
2. Annotate 21 clips (about 1.5–2 h) once the fixed `annotate_clip.py` is delivered (around hour 4).
3. About 40 min of live testing in Phase E.
4. Approve the final commit.

## Verification
- `pytest backend/tests models/tests` all green, the real-clip parity test passes, and `vite build` exits 0.
- `metrics.json`: 7 subjects, human labels, inner-tuned threshold (no fold `inner_f1 = 0` fallback), CIs and baselines. A same-seed rerun is byte-identical.
- Replay benchmark: the new pack beats the old pack on span detection rate at ≤0.5 FA/min on natural clips (targets; report honestly if missed).
- Intervention scenario tests all pass. A simulated never-answering child escalates tier 1 → 2 → 3 → 4, and an answering child de-escalates.
- The app shows `ml_mode=model6` with pack v4. Removing the pack gives a loud warning and `ml_mode=rule`, and rule-mode prompts are capped at tier 2.
