# Fusion Model — Video Requirements & Training Plan

## Why new videos are needed

The current fusion model (`models/src/model5_fusion/`) was trained on **3 videos of (effectively) one setup** —
`natural`, `forced`, `distracted` — totalling only **800 windows** (train 560 / val 120 / test 120,
`data/processed/model5_fusion/*.csv`). Two fatal flaws, confirmed in
[PLAN_1](PLAN_1_model_accuracy_and_natural_distraction.md):

1. Labels come from the **filename** (a whole video is "distracted" or "focused"), and `natural.mp4` is
   labelled **all focused** — so the model is taught that natural distraction = focus.
2. The split is **random per window** (overlapping windows), so the reported 100% test score is leakage.
   The honest leave-video-out result was ROC-AUC 0.77 / F1 0.54 (`models/fus_out.txt`).

More windows from the same 3 videos cannot fix this. The model needs **more people**, each recorded in
**one mixed session** containing both focused and naturally distracted behaviour, so it can be trained and
tested **leave-one-subject-out (LOSO)** — on people it has never seen.

---

## The video list — what to provide

### How many

| Tier | Participants | Videos (1 session each) | Total footage | What it supports |
|---|---|---|---|---|
| **Minimum** | 8 | **8 videos** | ~3 hours | LOSO training works, results indicative only |
| **Recommended** | 15 | **15 videos** | ~5–6 hours | Defensible LOSO numbers for the thesis (target) |
| **Ideal** | 20 | **20 videos** | ~7–8 hours | Tighter mean ± std across subjects |

You may split each session into task clips (reading / lesson / quiz / scripted) — e.g. 4 clips per person =
32 / 60 / 80 files. Total duration and one-person-per-session are what matter, not file count.

### One video per participant must contain (≈20–25 min)

| Segment | Duration | Notes |
|---|---|---|
| Calibration | ~10–30 s | Look at centre + 4 corners of the screen when prompted |
| Reading on screen | ~8 min | Normal behaviour, do not act |
| Video lesson | ~8 min | Normal behaviour, do not act |
| Quiz / typing | ~5 min | Normal behaviour |
| Scripted block (end) | ~3 min | Deliberately: use phone, turn & talk, look away ≥5 s, close eyes, leave seat — guarantees examples of rare classes |

Rules that matter more than quantity:

- **Mixed content in every video.** Never send one all-focused video and one all-distracted video, and never
  name files `distracted.mp4` / `focused.mp4` — filename labelling is the bug being fixed.
- **Natural behaviour for most of the session.** Leave a phone on the desk; don't script distraction outside
  the final 3-minute block.
- **Different people > same person twice.** 15 people × 1 session beats 5 people × 3 sessions, because the
  test is "does it work on a new person".
- If possible, run a **thought probe** every ~3 min ("Just now, were you focused? Yes / Kind of / No") and
  save the answers with timestamps — this is the only ground truth for mind-wandering. Optional but valuable.

### Event coverage needed across the dataset

The model learns these classes (Plan 1 definitions). Across all videos combined we need roughly:

| Class | Minimum episodes (total) | Notes |
|---|---|---|
| `on_task` | the majority of every video | Comes free |
| `glance` (<2 s look-away) | 100+ | Comes free, must be labelled so it is *not* punished |
| `look_away` (≥2 s) | 50+ | Natural + scripted block |
| `phone_object` | 30+ | Scripted block guarantees these |
| `talking_social` | 30+ | Needs a second person nearby, or phone call acting in scripted block |
| `fidget_restless` | 30+ | Mostly natural |
| `drowsy_zoneout` | 20+ | Hardest to get naturally; scripted eye-close helps |
| `absent` (no face ≥3 s) | 20+ | Scripted block guarantees these |

### Technical spec per video

- Format: `.mp4` (H.264), **640×480 minimum** (720p preferred), **15–30 fps**, constant frame rate if possible
- Framing: face + shoulders fully visible, webcam roughly at screen level, face not backlit, no beauty
  filters / virtual backgrounds / Snapchat-style effects
- Audio: keep it if available (helps verify `talking_social` during labelling), not used as a model feature
- One participant per video; note if they wear **glasses** (needed for analysis)

### File naming + metadata (important)

```
videos/
  S01/S01_session.mp4        (or S01_reading.mp4, S01_lesson.mp4, ...)
  S02/S02_session.mp4
  ...
  metadata.csv
```

`metadata.csv` columns: `subject_id, file, duration_sec, fps, resolution, glasses (y/n), lighting (good/dim/backlit), camera_position, consent_confirmed (y/n), notes`

Also required before recording anyone: a signed/recorded **consent** per participant, and check with your
supervisor whether faculty ethics approval is needed. No consent = we cannot use that video.

---

## Training plan (once videos arrive)

### Phase 0 — Intake & validation (0.5 day)
- Inventory files against `metadata.csv`; probe each with ffprobe (duration, fps, resolution, corrupt frames).
- Reject/flag: face not visible, heavy backlight, wrong person count, missing consent.
- **Gate:** at least 8 valid participants, every event class above minimum episodes (estimate from scripted blocks).

### Phase 1 — Honest baseline (0.5 day)
- Re-score the *current* fusion model grouped by video (no window-level random split) and save the numbers.
  This is the "before" column for the thesis. Back up current `model.pkl` first.

### Phase 2 — Pipeline fixes (1–2 days, before touching new data)
- `models/src/model5_fusion/prep.py` / `prepare.py`: delete filename-based weak labelling and the
  window-level random split; split by `subject_id` (LOSO).
- `models/test_fusion_video.py`: delete the filename prediction override (`"distracted"` in name → 0.88).
- Decide feature path (recommended, per Plan 1): shared MediaPipe feature extractor
  (`models/src/features/` — head pose from face matrix, iris ratio, blink/PERCLOS, jaw, pose motion,
  per-user calibration) producing per-frame features. The old gaze/pose/engagement CSV merge is kept only as
  the baseline pipeline for comparison.

### Phase 3 — Labelling (3–6 days, overlaps Phase 2; ~3× real time)
- Label event start/end per video with the classes above. Tool: `models/scripts/label_tool.py` (to be built)
  or CVAT/ELAN if preferred.
- Thought-probe answers (if collected) are merged as mind-wandering labels.
- Double-label ~20% of minutes by a second person; report **Cohen's κ** (target ≥ 0.7).
- Output per video: `labels/Sxx_labels.csv` (`start_sec, end_sec, class`).
- **Gate:** κ ≥ 0.7 on double-labelled portion; every class ≥ minimum episodes; otherwise collect/label more.

### Phase 4 — Window dataset (0.5–1 day)
- Per-frame features → windows of 2 s / 5 s / 10 s at 1 s hop with temporal features: on-screen ratio,
  current off-screen dwell, glance count, blink rate, PERCLOS, face-present ratio, motion energy,
  hand-to-face, talking score, plus interaction signals if recorded in the LMS.
- Output: `models/data/processed/model6_natural/windows_<2|5|10>s.csv`
  (`subject_id, window_start_sec, <features>, y_binary, y_class`).
- Sanity checks: class balance per subject, no subject in two splits, feature distributions per class plotted.

### Phase 5 — Training (0.5 day; measured fit time is minutes, not hours)
- Classifier: **LightGBM** (logistic regression + rule-based gate as baselines; old fusion as baseline).
- **LOSO cross-validation**: 8–20 folds, one fold per held-out participant.
- Temporal smoothing + hysteresis on probabilities: enter distracted at p > 0.6 sustained ≥ 3 s,
  exit at p < 0.4 for ≥ 2 s; glances < 2 s never trigger.
- Tune the operating point on **false alarms per 10 min**, not just accuracy.
- Expected compute (from the 2026-10-20 benchmark): one LOSO pass ≈ seconds–minutes on CPU;
  the full window/baseline/ablation sweep < ~2 h. Training time is *not* the bottleneck — labelling is.

### Phase 6 — Evaluation & comparison (1 day)
Report mean ± std across held-out subjects:
- Window level: macro-F1, ROC-AUC, PR-AUC
- **Event level: F1** (episode overlap), **false alarms / 10 min**, **detection latency (s)**
- Thought-probe agreement (if probes collected)
- Ablations: no calibration · no interaction signals · own CNN gaze/pose vs MediaPipe · no temporal smoothing
- Confusion focus: `glance` vs `look_away`
- Side-by-side table vs Phase 1 honest baseline (old fusion: ROC-AUC 0.77 / F1 0.54, and gaze Model 1
  retrained 2026-10-21: 60.2% acc / F1 0.559 on MPIIGaze test).
- Save: `models/reports/model6_natural/loso_metrics.json` + confusion matrices + per-subject table.

### Phase 7 — Integration & live verification (2–3 days)
- Package model to `models/outputs/checkpoints/model6_natural/model.pkl` + `meta.json`
  (feature order, thresholds, window config).
- Wire into `backend/app/services/ml_service.py` (shared extractor, per-session calibration, rolling
  buffer, hysteresis state), Socket.IO telemetry path, episode duration into
  `backend/app/services/intervention_engine.py`. `UNKNOWN` (not FOCUSED/DISTRACTED) on bad input/no light;
  `absent` only after 3 s without a face.
- Replay test on one held-out participant recording (predicted vs labelled episode timeline plot).
- Live test script: glance (no trigger) → look away 5 s+ (intervention fires) → phone (escalation) → return
  (episode closes). `pytest backend/tests` stays green.

### Indicative timeline after videos + labels are ready

| Day | Work |
|---|---|
| 0.5 | Intake/validation, honest baseline |
| 1–2 | Pipeline fixes (filename labels, split, overrides) |
| 3–6 | Labelling + κ (the long pole; can start as soon as first videos land) |
| 7 | Window dataset + training (LOSO) |
| 8 | Evaluation, ablations, comparison table |
| 9–11 | Backend integration, replay + live verification, write-up |

Fallback order if time runs out (per Plan 1): fewer participants (stop at 8) → drop optional GRU/L2CS →
never drop LOSO evaluation or per-user calibration.

---

## What I need from you to start

1. The videos, in the structure above, with `metadata.csv` and consent confirmed.
2. Say whether thought probes were collected (and where the answers are stored).
3. Say who labels: you / a friend for the double-labelled 20% / me to build the labelling tool so you can label.

As soon as the first batch lands I can run Phase 0 (validation) and Phase 1 (honest baseline) the same day.
