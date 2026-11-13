# PLAN 3 (rev. 2): finish remediation, then retrain model6 on 7 participants. 72-hour budget

## Context
**What's already on branch `expert-remediation` (uncommitted):**
- Nested-LOSO trainer.
- Head-pose axis fix.
- One shared training/live feature path (`models/src/features/live.py`, backend `predict_frames`, 2 fps frontend).
- Backend hardening and documentation fixes.

**Why the model needs retraining:** the old labels were rules over the model's own features, which is circular. The axis fix proved it: S02's positives went from 5 to 0. So model6 must be retrained on **human labels**.

**The data** (`D:\uni\6th sem\IRP\Data collection\raw data`):
- P1–P7, all with consent.
- Each has focused (named `forced` for P2/P3), distracted and natural clips: about 110 min in total, 3–10 min per clip.
- Distracted clips are distracted throughout.

**Confirmed decisions:**
- **Labels:** human timestamp annotation of the exceptions only. Natural clips are fully annotated and used for evaluation only.
- **Engagement:** `engagement_score = 1 − P(distracted)`. No separate model.
- **M1/M2/M3:** not retrained.

**Deliverable doc:** after approval, overwrite `dev/PLAN_3_model_training_v3.md` with this plan, updating the earlier 6-participant version.

## Data notes
| P | Clips | Note |
|---|---|---|
| S01 | focused 5.3 / distracted 5.1 / natural 3.0 min | 720p 15 fps |
| S02 | forced 5.1 / distracted **1.6** / natural 4.7 | 360p; few positives |
| S03 | forced 5.2 / distracted 5.1 / natural 3.1 | fps differs per clip |
| S04 | focused 3.1 / distracted 3.0 / natural 3.0 | 10–15 fps |
| S05 | **focused.MOV 1080p** 5.1 / distracted 5.7 / natural 3.4 | focused clip from a different camera (confound) |
| S06 | focused 10.6 / distracted 6.1 / natural 6.3 | |
| S07 | Focused 5.0 / distracted 3.0 / Natural 5.0 | capitalised names |

## Phase 0: stabilise (hours 0–3)
- **Interrupted tests:**
  - Run `backend/tests/test_s3_fusion_runtime.py` + `test_feature_parity.py` with `-o faulthandler_timeout=60`, logging to the scratchpad.
  - Then run the full backend suite and find the earlier stall near `test_security_access`.
  - Fix any failures. Run `models/tests`.
- **Frontend:** `npx vite build`.
- **Commit checkpoint** on `expert-remediation`, after user approval.

## Phase 1: intake, feature cache, annotation tool (hours 3–8)
- **`models/src/model6_natural/intake.py`:** match file stems case-insensitively and accept `.mp4`/`.mov`. `FOCUSED_NAMES` already covers `forced`. Add resolution, fps and duration to the manifest.
- **New `models/src/model6_natural/cache_frames.py`:**
  - For each clip, `FrameFeatureExtractor` at 2 fps (`extract._iter_sampled_frames`) writes per-frame rows (the FrameFeatures fields) to `models/data/processed/model6_natural/frames/<S0x>_<cond>.csv`.
  - Restartable. Run it in the background (CPU, about 13k frames).
- **`extract.py`:** add a mode that builds windows from the cached frames.
  - Windows: `windows.windows_from_frames`, 5 s, 1 s hop.
  - Pose baseline: `compute_pose_baseline` on the subject's focused clip.
  - Labels: `label_from_segments` (exists, tested). Segments = the clip default (focused 0, distracted 1, natural 0) overlaid with annotated spans. Windows below 80% coverage are dropped.
  - Natural rows get `eval_only=1`.
  - Meta: `label_source="human_annotation"`.
- **New `models/scripts/annotate_clip.py`** (OpenCV player):
  - Speeds 1/2/4×; keys `D`/`F` toggle a distracted/focused span, `Space` pauses, `←/→` seek 2 s.
  - Writes `<clip>_labels.csv` (`start_sec,end_sec,label`) next to the clip, outside the repo.
  - Printed definition: off-screen attention of 2 s or more (phone, looking away, talking, absent, drowsy). Glances under 2 s are not distraction.

## Phase 2: annotation (user, about 1.5 h, alongside Phase 1)
- **Distracted clips:** mark on-task spans of 3 s or more.
- **Focused clips:** mark distraction spans of 3 s or more.
- **Natural clips:** mark every distraction span.
- Optional: a second annotator on 2 natural clips, to report Cohen's κ.

## Phase 3: train + evaluate (hours 10–20, GPU)
**`models/src/model6_natural/train.py`:**
- Respect `eval_only`: those rows are excluded from `select_hyperparams` inputs and from final fitting, scored per held-out subject, and reported separately.
- Add packing logistic regression as the deployed model if it beats the MLP on mean nested-LOSO F1+ (rule fixed in advance).

**Run:** `--windows <human windows csv> --out-dir models/reports/model6_v3/human_labels`.

**Report:**
- Per-subject and mean ± std, with a bootstrap 95% CI over the 7 subjects, of F1+, precision, recall, PR-AUC, ROC and Brier.
- Baselines: majority, the `distraction_proxy` rule, logistic regression.
- Natural-clip event metrics with hysteresis: false alarms per minute, and the detection rate of annotated spans.
- Ablations by feature group.
- S05 reported separately, plus a run with S05 excluded (camera confound).
- Reliability plot.

**Deploy:** `deploy()` → `models/outputs/checkpoints/model6_v3/model.pkl` (`version=v3_nested_loso`, median inner threshold and hysteresis).

## Phase 4: integration + live check (hours 20–32)
- **`backend/app/services/ml_service.py::_decide_live`:** add `engagement_score = round(1 − dist_prob, 4)`. Label engagement on `frontend/src/pages/teacher/TeacherAnalytics.jsx` as derived.
- **Tests:**
  - Parity on a real clip: `MODEL6_PARITY_CLIP=<P1 clip> pytest backend/tests/test_feature_parity.py`.
  - The full suite.
- **Latency:** `evaluation/thesis_numbers/run_heartbeat_latency.py` with 4-frame heartbeats, CPU + CUDA, median and p95.
- **Live self-test with the user (about 30 min):** `evaluation/thesis_numbers/live_webcam_selftest.py` phases. Record `ml_mode=model6` and `inference_path`, and compare with the Table 6.15 targets.

## Phase 5: write-up (hours 32–56)
**New `evaluation/thesis_numbers/REPORT_10_REMEDIATION.md`:**
- Problems found, the changes, the new numbers with CIs, baselines, ablations, natural-clip events, latency and the live test.
- Hashes from `git rev-parse`.

**New `evaluation/thesis_numbers/ERRATA_VIVA.md`:**
- Table 6.10 withdrawn (leakage).
- M4 at 97% withdrawn (circular).
- M1 numbers unchanged but not used live.
- Model6 v2 0.569 replaced.
- Table 6.7 and Table 6.15 replaced.
- n=1 live evidence becomes 7 offline subjects + a live check.

**Other docs:**
- `SYSTEM.md`: update the model6 v3 live pipeline, list the legacy models, and describe the data and labelling protocol.
- `dev/VIVA_NOTES.md`: slide outline.

## Phase 6: buffer (hours 56–72)
Re-annotation fixes, the camera-confound re-run if needed, and the final commit (after user approval).

**Cut order if behind:** κ → calibration → ablations → second live person.
**Never cut:** human labels, nested LOSO + baselines, natural clips for evaluation only, the parity test, the ERRATA sheet.

## User actions
1. Annotate (about 1.5 h) when `annotate_clip.py` is delivered.
2. Approve commits.
3. 30 min of live testing in Phase 4.

## Verification
- `venvpy312\Scripts\python.exe -m pytest backend/tests models/tests` all pass; the real-clip parity test passes.
- `metrics.json` has 7 subjects, baselines, CIs and natural-clip metrics; a same-seed re-run is identical.
- The app runs with `ml_mode=model6` and `inference_path=fusion` on the new pack. Renaming the pack gives `ml_mode=rule` with no constant confidences.
- REPORT_10, ERRATA_VIVA and SYSTEM.md are updated, and `dev/PLAN_3_model_training_v3.md` matches this plan.
