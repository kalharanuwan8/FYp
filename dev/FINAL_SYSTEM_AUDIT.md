# FINAL SYSTEM AUDIT — Luma Distraction-Detection LMS

**Audit date:** 2026-10-23  
**Scope:** Working tree of `distraction_project` as inspected for thesis evaluation.  
**Method:** Documentation (`SYSTEM.md`, `models/CHECKPOINTS.md`, `dev/PLAN_*.md`) treated as claims; code, checkpoint binaries, and existing logs inspected. Figures below were read from files or checkpoint metadata — **not recomputed**. No application code, checkpoints, or evaluation outputs were modified. No pytest suite was executed; no test is marked passed.

---

## 1. Version identification

### 1.1 Git identity

| Field | Value |
|-------|-------|
| Branch | `camtesting` |
| Commit | `f7bb5fa22c2fbf2ca46817db7302499eddbda0e9` |
| Commit date | 2026-02-24 |
| Commit message | Initial commit |

That commit does **not** contain the LMS. The working tree deletes the old root `src/` model layout and leaves `SYSTEM.md`, `backend/`, `frontend/`, `models/`, and `dev/` untracked. Checkpoints, CSVs, and reports are gitignored (`*.pt`, `*.pkl`, `outputs/`, `data/`, `reports/`, `*.csv`).

**The version that would be evaluated is this dirty working tree, not `HEAD`.**

### 1.2 Uncommitted changes relevant to application or models

- **Deleted** (relative to `HEAD`): old root-level `src/`, `scripts/`, `check_gaze_stats.py`, `check_mat.py`.
- **Untracked (application):** `SYSTEM.md`, entire `backend/`, entire `frontend/`, `dev/`.
- **Untracked (models):** current `models/` tree (training code under `models/src/`, harnesses, logs under `models/reports/`).
- **Present but gitignored (evaluation assets):** checkpoints under `models/outputs/checkpoints/`, processed CSVs under `models/data/`, MediaPipe task file, pickles, and generated reports.

### 1.3 Checkpoint paths, SHA-256 hashes, and training metadata

Live weights are loaded by `backend/app/services/ml_service.py` (env overrides: `GAZE_CKPT`, `POSE_CKPT`, `ENG_CKPT`, `FUSION_CKPT`). Paths below are relative to `models/`.

#### Gaze (M1) — default `outputs/checkpoints/model1_gaze/best.pt`

| Property | Value |
|----------|-------|
| SHA-256 | `8127a926c74a21b41f4398d43f8a662c653f61e31f2dd62302cd995b442eba32` |
| Size | 27,089,538 bytes |
| File time | 2026-10-21 07:34:17 |
| Metadata | epoch **15**, `img_size` **96**, 4 classes (`center`/`left`/`right`/`down`), `best_f1` 0.569808 |

Identical hash to `last.pt` and `last_epoch15_96_backup.pt`. The stored `best_f1` is the **epoch-2 validation peak** (training log val F1 ≈ 0.5698), not this epoch’s validation F1 (≈ 0.5423).

Epoch-2 backups (not the default load path):

| File | SHA-256 (prefix) | Notes |
|------|------------------|-------|
| `best_epoch2_backup.pt` | `a3e1f4ed…` | 9,143,300 bytes; epoch 2; `img_size` 224; 2026-07-01 |
| `last_epoch2_backup.pt` | `fbe931d3…` | epoch 2; `img_size` 224 |

#### Head pose (M2) — default `outputs/checkpoints/model2_pose/best.pt`

| Property | Value |
|----------|-------|
| SHA-256 | `a91162707d5eff172e21f16cac93feeec9b57306dac1ca78531efd4e8050f629` |
| Size | 134,253,858 bytes |
| File time | 2026-02-16 09:09:31 |
| Metadata | epoch **3**, `best_val` 6.015167; **no** `img_size` key |

`last.pt` is a different file (`61104a6d…`, 2026-02-16 09:11:03) and is not the default.

#### Engagement (M4) — default `outputs/checkpoints/model4_engagement/model.pkl`

| Property | Value |
|----------|-------|
| SHA-256 | `d39b5f16d3e78653c06fdead842518e2d6add967194474de6f632373beb237e9` |
| Size | 2,419 bytes |
| File time | 2026-07-22 06:50:55 |
| Metadata | Pipeline `StandardScaler` + logistic regression; 12 `feature_cols`; embedded hold-out accuracy **0.9736842105263158** on **76** samples |

#### Fusion (M5) — default `outputs/checkpoints/model5_fusion/model.pkl`

| Property | Value |
|----------|-------|
| SHA-256 | `b465e0c48af9067b9417a696a7c510ddf34ac98779d6aea6adba94e7d42020e6` |
| Size | 1,853 bytes |
| File time | 2026-07-26 15:08:42 |
| Metadata | **9** features; threshold **0.5**; `threshold_tuning.enabled` **false**; `class_weight` null; `C` 1.0; `max_iter` 2000; scaler fitted on 9 columns |

#### MediaPipe task — `src/model4_engagement/pose_landmarker_lite.task`

| Property | Value |
|----------|-------|
| SHA-256 | `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a` |
| Size | 5,777,746 bytes |
| File time | 2026-02-16 10:12:18 |

---

## 2. Training versus live inference

Comparison of offline training / CSV producers versus the live backend path in `MLService` and the browser heartbeat.

| Aspect | Training / offline producers | Live backend / browser | Match? |
|--------|------------------------------|------------------------|--------|
| **Fusion feature names & order** | Pickle + `data/processed/model5_fusion/meta.json`: `p_center_mean`, `p_left_mean`, `p_right_mean`, `p_down_mean`, `gaze_away_ratio`, `yaw_mean`, `pitch_mean`, `roll_mean`, `engagement_prob_mean` (**9**). Candidate list in `models/src/model5_fusion/prep.py` also names `yaw_std`, `pitch_std`, `roll_std`, but pose CSVs never emit them so they are dropped. | `FUSION_FEATURES_DEFAULT` lists all **12**; overwritten by pickle `features` when present. `build_fusion_features` computes stds then indexes `fusion_feat_names` — live stds are **discarded** for this checkpoint. Missing name → `0.0`. | Names: match for loaded pickle. Live still computes unused stds. |
| **Feature count** | 9 (scaler `n_features_in_=9`) | 9 when pickle loaded; would send 12 if `features` key missing | Match when pickle present |
| **Feature scaling** | `StandardScaler` inside sklearn `Pipeline` (`train.py`); `fillna(0.0)` before fit/predict | Calls `predict_proba` on the pipeline (scaler runs). NaN already in a live dict value is **not** filled. | Scaler: match. Fill: partial mismatch |
| **Missing-feature handling** | Training rows: `fillna(0.0)`. Ambiguous weak labels dropped (`y == -1`). | `dict.get(name, 0.0)` for absent keys only | Partial |
| **Fusion threshold** | Stored in pickle as `"threshold"`. Current disk pickle: **0.5**, tuning disabled. (`fus_out.txt` reports 0.745 for a **different** historical package.) | `self.fusion_threshold = float(pack.get("threshold", 0.5))`; decision `dist_prob >= self.fusion_threshold` (`ml_service.py` ~200, ~521). No threshold env var. | Match for current pickle (0.5) |
| **Gaze input size** | Deployed train config / checkpoint: `img_size` **96** (`dataset.py` `GazeDataConfig`). Epoch-2 backup used 224. | Reads `ckpt.get("img_size", 224)` | Match for current best.pt |
| **Gaze eye / face crop** | MPIIGaze **normalised eye patches** for M1 train. Fusion gaze CSVs from `model1_gaze/infer.py`: **full video frame** → grayscale (`infer.py` ~64), no Haar eye crop. | Haar face `minSize=(50,50)`, Haar eye `minSize=(12,12)`; else top half of face (`detect_eye_crop`, ~246–259). Browser: 320×240 camera → 224×224 JPEG every 2000 ms (`useMonitoringSession.js` ~147–151, ~194–198). | **Mismatch** |
| **Head-pose preprocessing** | BIWI: full frames resized to 224; targets in **degrees**. Fusion pose CSVs: centre **60%** crop, means only (`model2_pose/infer.py` ~30–39, ~142). | Haar face crop + 15% pad, else centre 60%; resize hardcoded 224; raw degrees; **no** baseline subtract (`ml_service.py` ~160–164, ~261–279). | **Mismatch** (train full frame / CSV centre-60% vs live Haar face) |
| **Calibration** | `prep.py` / `train.py`: none. Optional `scripts/extract_calibrated_features.py` and `test_fusion_video.py`: 1 s baseline, pose subtract, +2.0 centre-logit boost. Whether July 2026 CSVs used that script is **not** in `meta.json`. | No calibration | Match to `prep`/`train`; mismatch if calibrated producer was used |
| **Window size** | Gaze/pose/engagement: **2.0 s** windows over video frames | Last `ML_WINDOW_FRAMES` heartbeats, default **3** (~4 s span at 0.5 Hz), not a 2 s video-rate window (`ml_service.py` ~91–92, ~582–589) | **Mismatch** |
| **Stride** | **1.0 s** between windows | No stride; rolling last-N frames | **Mismatch** |
| **Sampling interval** | Video FPS (every frame inside window) | Heartbeat **2000 ms** | **Mismatch** |
| **Timestamp handling (MediaPipe)** | Per-video detector; `timestamp_ms = int((n-1)/fps*1000)` (`extractpose.py`) | One process-wide `VIDEO` landmarker; `timestamp_ms = int((time.time()-session_t0)*1000)` (`ml_service.py` ~210–222, ~470–474) | **Mismatch** |
| **Engagement features** | Same 12 names. Formulas over frames in `[start, start+2)`. Windows with **`< 5`** rows **dropped** (`buildfeatures.py` ~13–40). Speed = displacement between consecutive **video** frames. | Same 12 names in `compute_engagement_features`. If **`n < 4`** valid landmarks: constants (`0.0` / `0.5` / `0.3` / `0.5`) instead of computing (`ml_service.py` ~321–330). Default window cap 3 ⇒ **always** defaults. | Names match; **values do not** |
| **Engagement min valid observations** | Skip window if `len(idx) < 5` | Defaults if `n < 4`; still scores with defaults | **Mismatch** |

**Note:** Increasing `ML_WINDOW_FRAMES` alone does **not** recreate training engagement features: heartbeats remain ~2 s apart, so wrist speed and related temporal features would still not match the video-rate definition.

---

## 3. Verify previously reported defects

Status key: **Present** | **Fixed** | **Not applicable** | **Unverified**.  
“Present” means the code path still exists. None of these were re-executed as automated tests in this audit.

| # | Defect | Status | Evidence |
|---|--------|--------|----------|
| 1 | Engagement features remaining at defaults because the live window is too short | **Present** | `ML_WINDOW_FRAMES` default 3 (`ml_service.py` ~91–92); slice to last `window_size` (~586–589); `n < 4` returns constant vector (~321–330). Training drops windows with `len(idx) < 5` (`buildfeatures.py` ~38–40). |
| 2 | Shared MediaPipe timestamps failing across sessions | **Present** (code path; failure mode **Unverified** at runtime in this audit) | One `PoseLandmarker` in `VIDEO` mode (~210–222). Per-session clock resets to 0 (~470–472). `clear_session` pops buffers/`_session_t0` but does not recreate the landmarker (~240–242). `extract_landmarks` swallows exceptions → `None` (~281–303). Later/overlapping sessions can fail `detect_for_video` until elapsed time exceeds the previous timestamp. |
| 3a | Missing faces producing misleading focus verdicts | **Fixed** (frame path) | No face → `DISTRACTED`, 0.92, `reason: no_face` (~591–598). |
| 3b | Inference exceptions producing misleading focus verdicts | **Present** | `except` in `predict_frame_image` → `FOCUSED`, 0.80, `face_detected: True` (~601–603). `predict_window_features` defaults `face_detected` to true and engagement to 0.80 (~609–615). |
| 4 | Unmonitored / unobserved periods reported as fully focused | **Present** | `compute_session_focus_percentage`: wall-clock minus distracted episodes (`focus_metrics.py` ~12–37). Gaps with no heartbeats stay in the focused share. Zero-length / invalid interval returns **100.0**. |
| 5 | Students able to modify guardian consent | **Present** (API) | Admin-only: `PATCH /api/auth/students/<id>/consent` (`auth.py` ~146–149). Student can write via `PATCH /api/student/profile` (`student_profile.py` ~121–146). Settings UI displays the flag only; API still accepts `consent_given`. `test_student_profile.py` expects student write to succeed — **not run** in this audit. |
| 6 | Gentle ambient cues unexpectedly pausing video | **Present** (video player) | `VideoLearningPlayer.jsx` pauses on every intervention (~35–44, ~118–123). `AmbientCue` itself is non-modal; teacher copy still describes tier 1 as no content pause. |
| 7 | Milestone questions unrelated to current material | **Present** | Session stores module id; `_resolve_module_and_content_ids` returns content id `None` (`session.py` ~125–130). `_pick_milestone_item` takes first active bank item in the **module** (~133–149). Empty bank → hardcoded “What is the main idea of this material?” (~167–180). LLM not called at intervention time. |
| 8 | Filename-based prediction overrides in evaluation / demonstration scripts | **Present** | `models/test_fusion_video.py` ~346–351: stems with `focused`/`forced`/`natural` cap `dist_prob` at 0.15; `distracted` floor at 0.88. **Not** in `run_tests.py`. Separate labelling issue: `prep.py` `weak_label` still starts from video stem. |
| 9 | Repeated session-stop requests awarding duplicate XP | **Present** | Ending session guarded by `if session.end_time is None` (`session.py` ~574–579). `award_session_xp` called on **every** stop (~605–612) and always adds XP (`gamification_service.py` ~156–161). |
| 10 | Disabling all intervention tiers failing to disable interventions | **Present** | `enabled_tiers()` → `[]` when all flags false. `_get_enabled_tiers`: `cfg.enabled_tiers() or [1, 2, 3, 4]` (`session.py` ~72). `InterventionEngine.__init__`: `enabled_tiers or [1, 2, 3, 4]` (`intervention_engine.py` ~72). Empty list coerced to all tiers on. Non-empty subset does fall back. |

---

## 4. Available evaluation evidence

**These logs were not re-run for this audit.** The fusion pickle on disk does **not** match the April `fus_out.txt` package.

### 4.1 Test / evaluation logs

| Artifact | Date | Checkpoint / split / threshold | Contents | Missing |
|----------|------|--------------------------------|----------|---------|
| `models/gaze_out.txt` | 2026-04-06 | — | Header only | Metrics, checkpoint, split, threshold, date inside file |
| `models/eng_out.txt` | 2026-04-06 | Implied M4; 76 samples; no path | Acc 0.9737, macro-F1 0.9732, ROC-AUC 0.9979; CM `[[32,2],[0,42]]` | Checkpoint path, split id, date, row list; labels are rule-based (`labelweak.py`) |
| `models/fus_out.txt` | 2026-04-06 | Threshold **0.745** (tuned); 82 windows (27 / 55) | @0.50: Acc 0.6829, F1 0.5357, ROC-AUC 0.7677, PR-AUC 0.5203; @0.745: F1 0.0000, Rec 0.0000; CM focused 53/2, distracted 27/0 | Checkpoint path; protocol name (file does **not** say leave-video-out); 82-row manifest; **not** the current pickle |
| `models/reports/accuracy_check_2026-10-20.txt` | 2026-10-20 | Gaze printed epoch **2**; pose epoch 3; fusion thr **0.500** untuned; fusion test **120** (45/75) | Gaze Acc 0.5669 / F1 0.5369; pose MAE yaw 6.85 / pitch 5.21 / roll 5.72 (mean 5.93); eng repeats 76-row scores; fusion Acc/F1/AUC/PR all **1.0000** then `UnboundLocalError` on `f12` | Gaze block describes epoch-2 backup, **not** current `best.pt`; fusion summary marked crashed; PowerShell traceback interleaved |
| `models/reports/gaze_retrain_eval_2026-10-21.txt` | 2026-10-21 07:36 | Then: `best.pt` epoch 2 / 224; `last.pt` epoch 15 / 96 | Epoch-2: Acc 0.5669, F1 0.5369; Epoch-15: Acc 0.6017, F1 0.5594 | Current `best.pt` is now the epoch-15 file — first block is **not** a description of today’s default |
| `models/reports/gaze_best_eval_2026-10-21.txt` | 2026-10-21 07:45 | Epoch **15**, 5,996 samples | Acc **0.6017**, macro-F1 **0.5593**; CM saved | Small cell-count differences vs the other epoch-15 dump (~1 count); neither re-run |
| `models/outputs/reports/model1_gaze/confusion_matrix.png` | 2026-10-21 07:45 | Tied to later gaze eval | Confusion matrix image | Matches epoch-15 timestamp, not the 2026-10-20 epoch-2 run |
| `models/outputs/logs/model4_engagement/metrics.json` | 2026-07-22 (same as eng pickle) | 76 test samples | Acc 0.973684…; CM matches `eng_out.txt` | ROC-AUC not in JSON; no checkpoint path; row list not saved |

### 4.2 Dataset manifests / CSVs

| Artifact | Notes |
|----------|-------|
| `models/data/processed/model5_fusion/{train,val,test}.csv` + `meta.json` | `meta.json` time 2026-07-26 15:08:40. Verified counts: train **560** (distracted 211, forced 221, natural 128); val **120** (46/44/30); test **120** (45/52/23). **Every split contains all three videos** — stratified window split (`prep.py` ~149–163, `random_state` 42), **not** leave-one-video-out. `meta.json`: feature names only — **no** threshold, split protocol, or date. |
| Gaze / pose processed CSVs | Subject-wise splits described in training configs (gaze p00–p14; pose subjects 01–20). This audit did **not** re-count those CSVs. |
| Window dumps (`window_preds_*.csv`, `window_pose_*.csv`, eng `pred_*.csv` / `preds_*.csv`) | Predictions present; **no** metric summary / no official test-split prediction dump for gaze or pose. |
| Engagement `labeled.csv` | Rule-labelled; 76-row hold-out list **not** stored separately. |

### 4.3 Non-results / missing evidence

| Item | Status |
|------|--------|
| `models/reports/model6_natural/training_time.json` | Marked synthetic — **not** a result. No Model 6 checkpoint. |
| Audio (M3) evaluation | Absent (intentionally stubbed). |
| ROC-curve images | Not found. |
| `outputs/diagrams/accuracy_confusion_matrix.png` | From hardcoded array in `generate_diagrams.py` — **simulated**, not a model run. |
| Leave-video-out fusion prediction file for the 82-window run | **Missing**. |
| Checkpoint sidecars (config/args next to weights) | **Missing**; metadata lives inside pickles / torch dicts / `meta.json` features only. |

### 4.4 Documentation claims vs artifacts

- `SYSTEM.md` / `dev/PLAN_1` quote April fusion ≈ ROC-AUC 0.77 / F1 0.54 and call that run leave-video-out. The log supports **0.7677** and **0.5357** at threshold 0.50; it does **not** name the protocol; that checkpoint is **not** the file the backend loads.
- The only test log matching the **current** fusion pickle (threshold 0.5, untuned, 120-row mixed-video test) is `accuracy_check_2026-10-20.txt` with score **1.0000** on a leaked overlapping-window split.

---

## 5. Prioritised corrections

For each issue: smallest appropriate correction, and whether it requires **feature regeneration**, **retraining**, and/or **reevaluation**.

### 5.1 Issues that invalidate model measurements

| Issue | Smallest correction | Regen / retrain / reeval |
|-------|---------------------|---------------------------|
| Wrong gaze citation (epoch-2 vs deployed epoch-15 / 96 px) | Freeze and report hashes above; quote `gaze_best_eval_2026-10-21.txt` for deployed `best.pt`; do not cite epoch-2 block as the live gaze model | Citation only: none. Later retrain = new version |
| Citing `fus_out.txt` (0.745 / 82 windows) as live fusion | Do not cite as live result. Live pickle is thr 0.5 untuned; matching log is 120-window Acc 1.0 on mixed-video overlapping split — label as **leakage**, not thesis result. Valid measurement needs subject-wise or leave-one-video protocol | New split → **feature regen** + **M5 retrain** + **reeval** |
| Filename override in `test_fusion_video.py` | Remove override before any demonstration | Script change only; prior numbers from that script are invalid |
| Live fusion inputs ≠ training definition (crops, 2 s / 1 s video windows, engagement formulas, min 5 obs) | Align extractor with training definition. **Do not** assume raising `ML_WINDOW_FRAMES` alone fixes temporal features (samples remain ~2 s apart) | If live extractor matched to existing CSVs: no M1–M5 retrain, but **reeval** live path. If crops/windows change CSVs: **fusion feature regen** + **M5 retrain**. **M4 retrain** only if 12-feature definition changes. M1/M2 MPIIGaze/BIWI scores remain benchmarks only |
| Shared MediaPipe video timestamps across sessions | Strictly increasing timestamps, or one detector per session | No retrain if landmark math unchanged; **reeval** sessions measured under shared detector |
| Exceptions scored as FOCUSED with `face_detected: true` | Explicit unusable / unknown state; do not open a focused interval | No retrain; **reeval** sessions that included those frames |

### 5.2 Issues that affect consent or access control

| Issue | Smallest correction | Model impact |
|-------|---------------------|--------------|
| Student `PATCH /api/student/profile` can set `consent_given` | Ignore `consent_given` on student profile PATCH; keep writes on admin consent route; update profile test that expects student write | None |

### 5.3 Issues that affect intervention behaviour or analytics

| Issue | Smallest correction | Model impact |
|-------|---------------------|--------------|
| Duplicate XP on repeated stop | Award XP only inside `end_time is None` branch, or record one-time award | None |
| All tiers disabled still fires | Treat explicit empty enabled-tier list as no interventions (incl. noise); do not coerce `[]` → `[1,2,3,4]` | None |
| Ambient cue pauses video | Pause only for types defined to pause (`pacing_pause`, milestone, break, noise), not `ambient_cue` | None |
| Milestone not tied to current material | Store content id on session; select bank item for that material | None |
| Unobserved time counted as focused | Focus % over observed heartbeats; report unobserved separately | None; historical analytics need recompute; coverage was never stored |

### 5.4 Cosmetic improvements

| Issue | Smallest correction | Model impact |
|-------|---------------------|--------------|
| `run_tests.py` fusion summary `f12` crash | Fix the print after metrics already printed | Optional reeval; 2026-10-20 numbers already in log |
| `gaze_out.txt` header-only | Leave file; point readers to 2026-10-21 reports | None |
| Simulated diagram confusion matrix | Label as synthetic wherever shown | None |

---

## 6. Blockers before freezing the evaluation version

1. **No frozen evaluation snapshot.** LMS code and weights are uncommitted; weights are gitignored. Freeze a named commit or archive that records the four SHA-256 hashes above and states that gaze `best.pt` is the epoch-15 / 96 px file.
2. **No valid live fusion generalisation figure on disk.** The log that matches the current pickle is a leaked three-video window split with score 1.0; the live feature pipeline does not implement training windows, crops, or engagement features.
3. **Engagement accuracy 0.9737 recovers rule labels** on the same features — it must not be reported as human-labelled engagement accuracy.
4. **Gaze and pose benchmark logs do not measure Haar crops** used in the LMS.
5. **Pose landmarks can silently disappear** across sessions (shared MediaPipe video detector); **inference exceptions are stored as focused**.
6. **Focus percentage counts unobserved time as focused** — unsuitable as a study outcome until observation coverage is defined.
7. **A student token can set `GuardianConsent.consent_given`.**
8. **`test_fusion_video.py` still replaces model probability from the filename** — any figure produced with that script is not a model result.

---

*End of audit. No performance figures were invented; no tests were marked passed without execution evidence.*
