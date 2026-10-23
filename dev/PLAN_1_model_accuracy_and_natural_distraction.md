# PLAN 1 — Make distraction detection accurate, and detect *natural* distraction

## Context — what is actually wrong today

The models aren't just "not quite accurate". Today's pipeline can't tell real distraction from focus, and the good numbers come from artefacts. Fix the evaluation first, then the perception, then the data.

| # | Problem | Where | Effect |
|---|---|---|---|
| 1 | Fusion is trained on **3 videos of 1 person**, labels come from the **filename**, and the split is **random per window** (2 s windows / 1 s stride, so windows overlap 50%) | `models/src/model5_fusion/prep.py:47-75,151-163` | 100% test score = leakage. The honest leave-video-out run was ROC-AUC 0.77 / F1 0.54 (`fus_out.txt`) |
| 2 | `natural.mp4` is labelled **all focused** by design | `prep.py:45,70-72` | The system is taught that natural distraction = focus. The opposite of your goal |
| 3 | The demo script **overrides predictions using the filename** (`"distracted"` in the name → 0.88) | `models/test_fusion_video.py:346-351` | The annotated demo videos show the filename, not the model. Remove before any viva |
| 4 | Haar cascade path doesn't exist, so gaze always runs on the **full frame**, so gaze outputs ≈0.25 uniform | `models/scripts/extract_calibrated_features.py:42-44` | Gaze features carry no information |
| 5 | Gaze CNN saved at **epoch 2/15** (test macro-F1 0.54). Trained on normalised 36×60 MPIIGaze patches but fed Haar crops or whole frames at runtime | `models/src/model1_gaze/*`, `webcam_test.py:43-55` | Train/serve mismatch |
| 6 | Pose trained on full BIWI 640×480 frames (roll labels ±180°, likely a wrong Euler order), run on face crops | `models/src/model2_pose/prepare.py:57-82,129-134` | Unreliable angles on webcam input |
| 7 | Engagement labels are a hand-written rule, re-learned by logistic regression (circular 97%). In the backend, 3 frames give constant default features | `model4_engagement/labelweak.py:13-24`, `backend/app/services/ml_service.py` | Engagement adds nothing |
| 8 | Backend has **no calibration** and uses a 3-frame window at 0.5 fps. Fusion was trained on calibrated + "+2 center boost" probabilities. No face → DISTRACTED | `backend/app/services/ml_service.py:429-431,592-598` | Live verdicts don't match training |
| 9 | No temporal reasoning: every window is classified alone. No dwell time, glance counting, or hysteresis | fusion + `intervention_engine.py` | A 1 s glance looks the same as a 30 s phone break |
| 10 | Audio model (M3), `src/common`, `src/fusion` are empty stubs | `models/src/...` | Remove from claims or mark as future work |

**Goal:** a model that detects **natural, spontaneous distraction** in real study sessions, tested **leave-one-subject-out** (on people it has never seen), with honest numbers you can defend.

## Defining "natural distraction" (put this in the thesis)

Natural distraction = an attention lapse that happens **on its own** during a real learning task (not acted). Make it measurable with these event classes:

| Label | Operational definition | Intervene? |
|---|---|---|
| `on_task` | Eyes on screen / content, interacting or reading | — |
| `glance` | Off-screen gaze **< 2 s**, then returns | **No** (normal behaviour; count frequency only) |
| `look_away` | Off-screen gaze / head turned **≥ 2 s** | Yes, after a dwell threshold |
| `phone_object` | Looking at a phone or object in hands or on the desk | Yes |
| `talking_social` | Talking or turned to another person | Yes |
| `fidget_restless` | High body/hand motion, posture shifts, not on content | Soft only |
| `drowsy_zoneout` | Eyes closing (PERCLOS↑), long stare with no interaction (mind-wandering proxy) | Soft |
| `absent` | No face for ≥ 3 s | Yes |

Final binary target for the system: **distracted = look_away ∪ phone ∪ talking ∪ absent ∪ (drowsy/zone-out sustained)**. Keep the multi-class labels for analysis and for the thesis.

## Approach (recommended)

**Use robust pretrained perception plus your own data, temporal features, and a fusion model.** Your research contribution becomes the *natural-distraction fusion + temporal model + intervention policy*, evaluated on real subjects. Keep your MobileNet gaze / ResNet pose models as an **ablation baseline** in the report.

### Step 1 — Honesty and hygiene fixes (Days 1–2)
- Delete the filename override in `test_fusion_video.py:346-351`. Remove the unconditional `+2.0` center boost (`webcam_test.py:501-502`).
- Fix the cascade path using `cv2.data.haarcascades` (only needed for the baseline).
- Rewrite fusion splitting as **GroupKFold / leave-one-subject-out** on `subject_id` (and never split overlapping windows of one recording across train and test).
- Re-run the *current* pipeline under that split and record the honest baseline numbers. This becomes the "before" column in your report.

### Step 2 — One shared feature extractor (Days 2–4)
Create `models/src/features/` (a single module imported by **offline extraction, `webcam_test.py`, and `backend/app/services/ml_service.py`**). This removes the train/serve skew that caused bugs 4, 5, 8.
- **MediaPipe FaceLandmarker** (478 landmarks + iris + blendshapes + facial transformation matrix):
  - head yaw/pitch/roll from the transformation matrix (replaces the BIWI model at runtime)
  - iris position ratio within the eye (horizontal/vertical gaze proxy)
  - `eyeBlinkLeft/Right` blendshapes → blink rate, PERCLOS
  - `jawOpen` variance → talking
- **MediaPipe PoseLandmarker** (already used in `model4_engagement/extractpose.py`): shoulder/wrist motion, hand-to-face, posture lean.
- Optional: **L2CS-Net** pretrained gaze on the face crop, if iris ratio is too noisy (test on Day 4).
- **Interaction signals from the browser** (cheap and very strong): tab hidden (`visibilitychange`), mouse/keyboard idle seconds, video playing/paused, quiz answer activity.
- **Per-user calibration** (≈10 s at session start): show 5 dots (centre and corners), record head pose + iris ratio, and fit a personal "on-screen" ellipse. All gaze/head features become *deviation from the personal baseline*. This handles webcam placement and the "down = screen" problem.

Frame rate: process at **5–10 fps** (not one frame per 2 s).

### Step 3 — Collect real data (start Day 3, finish Day 10)
Protocol (write a 1-page ethics/consent sheet; ask your supervisor what approval you need):
- **8–20 participants**, around 20–25 min each, recorded *inside your LMS* (webcam 640×480 @ 15 fps + logged interaction events, timestamp-synced).
- Session: calibration → 8 min reading → 8 min video lesson → 5 min quiz. Leave a phone on the desk and allow normal behaviour; **don't script distraction** for most of the session.
  - Add a short **scripted block (~3 min)** at the end (look at phone, turn to talk, look away, close eyes) to guarantee positive examples of each class.
  - Add **thought probes** every ~3 min: a small popup asks "Just now, were you focused on the lesson? (Yes / Kind of / No)". This is the standard way to capture *mind-wandering* that cameras can't see, and it gives you natural ground truth.
- Store per-session `meta.json` (subject_id, camera position, lighting, glasses).

**Labelling** (Days 6–11):
- Use **CVAT** or **ELAN** (or a small OpenCV key-press labeller script, `models/scripts/label_tool.py`) to mark event start/end with the classes above.
- Double-label ~20% of the minutes by a second person and report **Cohen's κ** (examiners like this).
- Budget about 3× real time per minute of video. 15 people × 20 min ≈ 15 h of labelling, so split it with a friend or label only the camera-relevant classes.

**Optional public data:** DAiSEE (student webcam engagement) for extra *external validation* only. Don't depend on it given the timeline.

### Step 4 — Temporal features and model (Days 9–14)
- Per-frame features → windows of **2 s, 5 s, 10 s** at 1 s hop. For each: mean/std of gaze and head deviation, **on-screen ratio**, **current off-screen dwell time**, **glance count**, blink rate, PERCLOS, face-present ratio, body motion energy, hand-to-face ratio, talking score, tab-hidden ratio, idle seconds, video state.
- Classifier: **LightGBM/XGBoost** (fast, works with small data, gives feature importance for the thesis). Baselines to report: your old fusion, logistic regression, rule-based gate.
- Optional if time: a small **GRU/TCN over 10–20 s feature sequences**.
- **Temporal smoothing + hysteresis**: an EMA on the probability, then *enter* distracted when p > 0.6 for ≥ 3 s, *exit* when p < 0.4 for ≥ 2 s. Glances < 2 s never trigger. This is what makes it behave "naturally".
- Tune thresholds per **false alarms per minute**, not just accuracy (interventions that fire too often ruin the experience for a student with ADHD).

### Step 5 — Evaluation (Days 13–16)
- **Leave-one-subject-out** cross-validation; report mean ± std across subjects.
- Metrics: macro-F1, ROC-AUC/PR-AUC (frame/window), **event-level F1** (a detected episode counts if it overlaps a true one), **false alarms per 10 min**, **detection latency (s)**, and agreement with thought-probe answers.
- Ablations (great thesis material): without calibration; without interaction signals; own CNN gaze/pose vs MediaPipe; without temporal smoothing; per-modality importance.
- Confusion analysis per class (glance vs look_away is the interesting one).

### Step 6 — Integrate into the backend (Days 14–18)
- Rewrite `backend/app/services/ml_service.py` to use the shared `models/src/features` extractor and the new model (`models/outputs/checkpoints/model6_natural/model.pkl` + `meta.json` with feature order, thresholds, window config).
- Keep per-session state: calibration baseline, rolling 10–20 s feature buffer, hysteresis state.
- Switch the live path to the **already-built Socket.IO `telemetry_window` event** (`backend/app/socket_events/telemetry.py`) at ~5 fps with small 320×240 JPEGs (or landmarks only). Send interaction signals with each message. Keep the REST heartbeat as a fallback.
- Feed the intervention engine **episode duration from the hysteresis state** instead of raw per-frame verdicts (`backend/app/services/intervention_engine.py` thresholds 5/10/20/40 s stay).
- Handle uncertainty: on a processing error or bad lighting → `UNKNOWN` (no intervention), not FOCUSED/DISTRACTED. On no face → `absent` only after 3 s.

### Critical files
- Fix: `models/test_fusion_video.py`, `models/webcam_test.py`, `models/scripts/extract_calibrated_features.py`, `models/src/model5_fusion/prep.py`, `models/src/model5_fusion/train.py`
- New: `models/src/features/{face.py,pose.py,calibration.py,windows.py}`, `models/src/model6_natural/{prepare.py,train.py,eval_loso.py,infer.py}`, `models/scripts/record_session.py`, `models/scripts/label_tool.py`
- Integrate: `backend/app/services/ml_service.py`, `backend/app/socket_events/telemetry.py`, `backend/app/routes/session.py`, `frontend/src/hooks/useMonitoringSession.js`, `frontend/src/services/socketService.js` (already written, currently unused)

### 3-week timeline
| Week | Work |
|---|---|
| 1 | Hygiene fixes + honest baseline · shared feature extractor + calibration · recording tool · **start recording** (Day 3+) |
| 2 | Finish recording + labelling (κ) · temporal features · LightGBM + smoothing · LOSO eval |
| 3 | Backend/socket integration · threshold tuning on false-alarm rate · ablations, figures, write-up · demo rehearsal |

**If time runs out (fallback order):** drop GRU → drop L2CS → drop DAiSEE → reduce to 8 participants. **Never** drop LOSO evaluation or calibration.

### Verification
- `python -m models.src.model6_natural.eval_loso` prints the per-subject table and saves `models/reports/model6_natural/loso_metrics.json` + confusion matrices.
- Replay test: run `webcam_test.py` / a replay script on a held-out participant recording and compare the timeline plot of predicted vs labelled episodes.
- Live test: start the backend + frontend, run a monitored session, deliberately glance (no trigger), look away 5 s+ (T1 fires), pick up the phone (escalation), return (episode closes).
- `pytest backend/tests` stays green (especially `test_intervention_engine.py`, `test_session.py`).

