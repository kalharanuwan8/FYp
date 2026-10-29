# REPORT_7 — Full re-test after `thesis-final` (tag `thesis-final-v2`)

Rules followed: no invented or rounded-up numbers; Part 0.2 reference table locked before new test runs; no threshold/checkpoint tuning on test or self-test results; every failed/bad run kept; `pg_dump` taken before live work; thesis document not edited; application code not changed for this report (only the already-committed model6 work under `thesis-final-v2`).

Tagged evaluation commit: `2974633d05e35e5e54f9cf6654809b5df13d2a9c` (`thesis-final-v2`).

---

## Part 0: what changed, and the reference values

### 0.1 What changed since `thesis-final`

#### Commands (raw)

```text
git status --short
git log --oneline thesis-final..HEAD
git diff --stat thesis-final
git rev-parse HEAD
```

Raw captures: `evaluation/thesis_numbers/raw/report7_git_status.txt`, `report7_git_log.txt`, `report7_git_diff_stat.txt`, `report7_head.txt`.

At the start of Part 0 (before the `thesis-final-v2` commit), `HEAD` was still `e6c7b17ec6e448594c4229c751ebc7b781f86ec3` (= `thesis-final`), so `git log thesis-final..HEAD` was empty. Working tree already contained model6 + `ml_service` changes.

`git diff --stat thesis-final` (committed diff only; untracked not shown):

```text
 backend/app/__init__.py                 |  16 +++
 backend/app/services/ml_service.py      | 194 +++++++++++++++++++++++++++++---
 backend/tests/test_s3_fusion_runtime.py |   2 +
 models/src/model6_natural/__init__.py   |   7 +-
 4 files changed, 198 insertions(+), 21 deletions(-)
```

#### Commit and tag

```text
git commit … → [expert-remediation 2974633] Add model6 LOSO fusion pack and live hysteresis for thesis-final-v2.
git tag -a thesis-final-v2 -m "Thesis final v2: model6 natural LOSO fusion + live hysteresis"
```

| Item | Value |
|---|---|
| Commit | `2974633d05e35e5e54f9cf6654809b5df13d2a9c` |
| Tag | `thesis-final-v2` (annotated; `git show` confirms it points at that commit) |

#### Summary of changes (models / training / features / config / live pipeline)

| Area | Change |
|---|---|
| Models | New **model6** MLP fusion (`kind=model6_mlp`) preferred over model5 when `models/outputs/checkpoints/model6_natural/model.pkl` exists. M1/M2/M4/M5 weight files are **absent on disk** (see checkpoint table). |
| Training | `models/src/model6_natural/{intake,extract,relabel,train,wrapper}.py`: MediaPipe FaceLandmarker + pose windows → LOSO CUDA MLP; deploy pack if mean ROC/F1 beat honest baseline 0.77 / 0.54. |
| Features | `models/src/features/{face_pose,windows}.py` + `face_landmarker.task`; 14 window features (not the old 9 model5 columns). |
| Config / live | `ml_service.py`: load model6; approximate live features from heartbeat buffer; hysteresis enter 0.6/3 s, exit 0.4/2 s for `model6_mlp` only. Pack threshold **0.48000000000000004**. Env `ML_FUSION_THRESHOLD` still overrides after load. |
| Other | Flask `HTTPException` handler + `/` health in `backend/app/__init__.py`. Test forces `fusion_kind="model5"` in one threshold unit test. |

#### Checkpoint table

SHA-256 commands:

```text
Get-FileHash models\outputs\checkpoints\model6_natural\model.pkl -Algorithm SHA256
# M1–M5 paths: Test-Path … → False (files missing)
```

| Model | Checkpoint file | SHA-256 now | SHA-256 in thesis-final (REPORT.md) | Changed? | Training date (file mtime) | Epoch / iteration selected | How it was selected |
|---|---|---|---|---|---|---|---|
| M1 gaze | `models/outputs/checkpoints/model1_gaze/best.pt` | **Not measured** (file missing) | `8127a926c74a21b41f4398d43f8a662c653f61e31f2dd62302cd995b442eba32` | Unknown (absent) | Not measured | Not measured | Thesis: validation macro-F1; REPORT.md notes deployed bytes match epoch-15 `last.pt` |
| M2 head pose | `models/outputs/checkpoints/model2_pose/best.pt` | **Not measured** (file missing) | `a91162707d5eff172e21f16cac93feeec9b57306dac1ca78531efd4e8050f629` | Unknown (absent) | Not measured | Not measured | Thesis: best validation SmoothL1 (`epoch` field 3 in REPORT.md) |
| M4 engagement | `models/outputs/checkpoints/model4_engagement/model.pkl` | **Not measured** (file missing) | `d39b5f16d3e78653c06fdead842518e2d6add967194474de6f632373beb237e9` | Unknown (absent) | Not measured | Not measured | Deployed pickle not refit in thesis-final REPORT |
| M5 fusion (logistic) | `models/outputs/checkpoints/model5_fusion/model.pkl` | **Not measured** (file missing) | `b465e0c48af9067b9417a696a7c510ddf34ac98779d6aea6adba94e7d42020e6` | Unknown (absent); live path prefers model6 | Not measured | Not measured | Thesis: existing train pipeline; threshold 0.5, tuning disabled |
| M6 fusion (MLP, new) | `models/outputs/checkpoints/model6_natural/model.pkl` | `13AAA3391DA9D3A8A8F631A6997BBB96F98636786F45726C42A83C33523EC5C8` | n/a (did not exist) | **Yes (new)** | 2026-10-29 10:52:15 | Deploy: mean of LOSO fold thresholds = **0.48000000000000004**; weights from full labeled retrain (80 epochs default) | Deploy if mean LOSO ROC-AUC and F1+ beat 0.77 / 0.54; fold packs kept best F1+ fold for inspect; **ISSUE:** per-fold threshold from `_pick_threshold` on the **held-out subject test** (`train.py`) |

Companion files: `model6_mlp.pt` SHA-256 `BC9BA514576BE6291DD380EE0744E73F28F70AD9A3B3947B01B922CD444C9D05`; `model6_mlp_best_fold.pt` present (mtime 10:48:23).

#### Retrained model (model6) — data / split / labels / hyperparams

From `models/data/processed/model6_natural/windows.csv` and `models/reports/model6_natural/loso_metrics.json` (commands saved under `raw/report7_model6_windows_summary.txt`):

| Item | Value |
|---|---|
| Dataset | Participant clips under `D:\uni\6th sem\IRP\Data collection\raw data\participant {1,2,3}` mapped to S01–S03 (participant 4 empty / unused). Conditions: focused/forced, distracted, natural. |
| Samples | 4513 windows total; `in_train=1` → 2612 labeled; `y=-1` natural/ambiguous → 1901 |
| Per subject (all windows) | S01 1591; S02 1341; S03 1581 |
| Labels | **Feature rules** on recording condition (`label_window_row` / `relabel_dataframe` in `windows.py`): focused/forced → 0 when on-screen; distracted → 1 from dwell/on-ratio/hand-to-face/proxy; natural always unlabeled; plus focused-p90 proxy for distracted. **ISSUE:** labels derived from the same feature family the model consumes. |
| Split | **Leave-one-subject-out** on labeled rows (`in_train=1`); natural held for false-alarm / minute. Not a random window split. |
| Window lengths | CSV `window_sec` mean 3.491… (min 2, max 5). Train CLI default `--window-sec 5` filters to 5 s windows when training. |
| Pose baseline in training | Yes — `compute_pose_baseline` first 30 face-present frames per clip (`windows.py`). Live uses first **8** face-present frames (`ML_POSE_BASELINE_FRAMES` default). |
| Live window | Heartbeat buffer last `ML_WINDOW_FRAMES` default **5** (~10 s at 0.5 Hz). Training windows are **2 s and 5 s** MediaPipe aggregates, not “5 heartbeats”. **ISSUE: train/serve mismatch.** |
| Live feature construction | Approximations in `build_fusion_features`; `glance_count`, `blink_rate`, `perclos`, `talking_score` hard-coded **0.0** live. **ISSUE: train/serve mismatch.** |
| Architecture | `FusionMLP`: Linear(14→64)-ReLU-Dropout0.2-Linear(64→32)-ReLU-Dropout0.1-Linear(32→1); StandardScaler; sigmoid. |
| Decision threshold (pack) | `0.48000000000000004` (mean of LOSO fold thresholds). Live hysteresis separately uses enter **0.6** / exit **0.4**. |
| Where threshold chosen | **ISSUE:** `_pick_threshold` on each LOSO **test** subject’s probabilities (`train.py` lines 233–234); deploy uses mean of those fold thresholds. |

LOSO metrics (file `loso_metrics.json`, not re-tuned):

| Fold held-out | n_train | n_test | accuracy | f1_positive | f1_macro | roc_auc | threshold |
|---|---|---|---|---|---|---|---|
| S01 | 718 | 606 | 0.9570957095709571 | 0.9554794520547946 | 0.9570390890847221 | 0.9889734752639386 | 0.4700000000000001 |
| S02 | 1028 | 296 | 0.9290540540540541 | 0.3225806451612903 | 0.6425737450405382 | 0.9828178694158075 | 0.77 |
| S03 | 902 | 422 | 0.7985781990521327 | 0.42953020134228187 | 0.6536140215344503 | 0.8650273224043716 | 0.2 |
| **mean** | — | — | 0.8949093208923813 | 0.5691967661861222 | 0.7510756185532369 | 0.9456062223613726 | — |

Mean baseline LR on same folds: F1+ 0.4884131971720345, ROC 0.8940029965289603. Honest baseline constants in code: ROC 0.77, F1+ 0.54. `beats_honest_baseline`: true. Device: NVIDIA GeForce RTX 4050 Laptop GPU.

S02 distracted positives in labeled data: only **10** (crosstab) — **ISSUE:** fewer than 30 positives for that subject’s class balance on LOSO test.

---

### 0.2 Reference values (fixed before testing)

Flags: **ABOVE EXPECTED** / **BELOW EXPECTED** / **AT EXPECTED** (±2 pp, or ±0.2° MAE) / **ISSUE** / **NOT COMPARABLE**.

| Measure | Reference | Source |
|---|---|---|
| M1 gaze accuracy (4 classes, MPIIGaze test p13–p14) | 60.2%; chance 25% | Thesis Table 6.8; REPORT.md test accuracy 0.6017344896597732 |
| M1 macro-F1 | 0.559 | Thesis / REPORT.md 0.5593556663019074 |
| M2 head-pose MAE (BIWI test) | 5.93° | Thesis / REPORT.md mean of three MAEs 5.927910881663853 |
| M4 engagement | Accuracy 0.9736842105263158; Precision 0.9545454545454546; Recall 1.0; F1 0.9767441860465116; Macro-F1 0.9732205778717407 (25% hold-out of weak labels) | Thesis §6.4.4 / REPORT.md §3 |
| M5 fusion, original split | Accuracy/Precision/Recall/F1/ROC-AUC all **1.0** (n=120); confusion `[[75,0],[0,45]]` | Thesis Table 6.10 / REPORT.md §4a — **ISSUE (leakage) already documented historically** |
| M5 fusion, blocked temporal split | All **1.0** (n=119); `[[74,0],[0,45]]` | Thesis Table 6.10 / REPORT.md §4b |
| M5 vs labelling-rule baseline and gaze-only ablation | Fusion should beat both | Design target (rule baseline Acc 0.375 / F1 0.5454… on original test) |
| M5 on participant-independent test | macro-F1 ≥ 0.70 | Target set now (Part 0.2) |
| Live self-test, reading phases | ≥ 70% of heartbeats FOCUSED | Thesis Table 6.15 |
| Live self-test, false deliveries | ≤ 0.5 per scheduled reading minute | Thesis Table 6.15 |
| Live self-test, phone and head-away | ≥ 70% DISTRACTED; first intervention ≤ 15 s | Thesis Table 6.15 |
| Live self-test, out of chair | ≥ 70% UNKNOWN; no FOCUSED | Thesis Table 6.15 |
| Share of DISTRACTED in phone/away from fusion (not body rule) | Run 5 = 0 of 27; design target > 50% | Thesis Table 6.12 / `selftest_metrics_run5.json` |
| Heartbeat processing median (warm, full inference) | 91.8 ms CUDA; must stay well below 2,000 ms | Thesis Table 6.7 / REPORT.md 91.80050005670637 |
| Backend tests | 130 passed, 0 failed | thesis-final |

Run 5 anchors (for Part 4 side-by-side), from `raw/selftest_metrics_run5.json` session 94 (not Part 0.2 targets; comparison only):

| Phase | n | FOCUSED | DIST fusion | DIST body | UNKNOWN |
|---|---|---|---|---|---|
| read_1 | 22 | 10 | 11 | 0 | 1 |
| phone | 15 | 2 | 0 | 13 | 0 |
| away | 15 | 1 | 0 | 14 | 0 |
| out_of_chair | 15 | 2 | 0 | 1 | 12 |
| read_2 | 30 | 24 | 4 | 1 | 1 |
| false interventions / reading min | 1.0 (2 interventions / 2.0 min) | | | | |
| reading face true share | 0.9423076923076923 | | | | |
| observed_v1 focus % | 46.91830345147059 | coverage 58.40542339214008 | | | |

---

## Part 1: model-by-model evaluation (held-out data)

### Shared blocker

```text
Test-Path model1_gaze/best.pt → False
Test-Path model2_pose/best.pt → False
Test-Path model4_engagement/model.pkl → False
Test-Path model5_fusion/model.pkl → False
```

No fresh forward pass of M1/M2/M4/M5 is possible. Old-vs-new on the same test set: **Not measured**.

### M1 gaze

| Field | Value |
|---|---|
| What it is | MobileNetV2, 4-class gaze (center/left/right/down), input grayscale eye/face crop (train/deploy 96×96 in thesis REPORT). Live: eye crop → softmax. |
| Where in pipeline | `_infer_frame_signals` → rolling `gaze` deque → fusion features |
| How trained | See thesis-final REPORT.md (not re-run here) |
| How accuracy computed | Would be `evaluation/thesis_numbers/run_model_metrics.py` on MPIIGaze p13–p14 |
| Results now | **Not measured** — checkpoint missing |
| Flag | **ISSUE** (cannot verify deployed weights) |

### M2 head pose

| Field | Value |
|---|---|
| What it is | ResNet-18 regressing yaw/pitch/roll (degrees) |
| Where | `_infer_frame_signals` → pose deque → baseline subtraction → fusion |
| Results now | **Not measured** — checkpoint missing |
| Flag | **ISSUE** |

### M4 engagement

| Field | Value |
|---|---|
| What it is | sklearn model on 12 landmark-derived features → P(active_work) |
| Fallback | `compute_engagement_features`: if fewer than **2** valid landmark frames (`thesis-final`), default feature vector (see REPORT_5) |
| Results now | **Not measured** — checkpoint missing |
| Flag | **ISSUE** |

### M5 logistic fusion (thesis-final)

| Field | Value |
|---|---|
| Results now | **Not measured** — checkpoint missing; live prefers model6 |
| Historical refs | Part 0.2 table (Acc 1.0 original & blocked) — **ISSUE** leakage documented in REPORT.md |
| Participant-independent M5 | **Not measured** |

### M6 MLP fusion (current live fusion)

#### What it is

14-D MediaPipe window features → StandardScaler → FusionMLP → P(distracted). Live path: `inference_path=fusion`, `fusion_kind=model6_mlp`, then hysteresis.

#### How accuracy was computed

| Item | Value |
|---|---|
| Script | `python -m models.src.model6_natural.train` (metrics written at train time; **not re-run** for this report to avoid a second training run) |
| Evidence file | `models/reports/model6_natural/loso_metrics.json` |
| Test set | LOSO: each subject once; labeled windows only |
| Threshold | Per-fold F1+ grid on **test** subject; deploy mean 0.48… — **ISSUE** |
| Metrics | accuracy = mean(pred==y); F1+ = positive-class F1; macro-F1; ROC-AUC / PR-AUC from `predict` scores |

#### Results vs Part 0.2

| Metric | Value | Flag |
|---|---|---|
| LOSO mean macro-F1 | 0.7510756185532369 | **ABOVE EXPECTED** vs target ≥ 0.70 (participant-independent) |
| LOSO mean F1+ | 0.5691967661861222 | (no separate Part 0.2 row; beats honest 0.54) **ABOVE EXPECTED** vs honest F1 0.54 |
| LOSO mean ROC-AUC | 0.9456062223613726 | **ABOVE EXPECTED** vs honest 0.77 |
| S01 macro-F1 | 0.9570390890847221 | **ABOVE EXPECTED** (≥0.70) |
| S02 macro-F1 | 0.6425737450405382 | **BELOW EXPECTED** (≥0.70); **ISSUE** few distracted labels |
| S03 macro-F1 | 0.6536140215344503 | **BELOW EXPECTED** (≥0.70) |
| vs LR baseline mean F1+ | MLP 0.569… vs LR 0.488… | fusion beats LR baseline on mean F1+ |
| Original M5 Acc 1.0 split | **Not measured** (different features/model) | **NOT COMPARABLE** |
| Blocked temporal M5 | **Not measured** | **NOT COMPARABLE** |
| Labelling-rule baseline (M5-style) | **Not measured** for model6 feature space in this report | **Not measured** |
| Gaze-only / head-only / engagement-only / all-9 ablations | **Not measured** (model6 has different 14 features; M5 packs missing) | **Not measured** |

#### Coefficients

Model6 is **not** logistic regression. First-layer weight L2 magnitudes (command → `raw/report7_model6_weights.json`):

| Feature | L2 ‖W[:,j]‖ | mean \|W\| |
|---|---|---|
| gaze_dev_mean | 1.6650643348693848 | 0.17618219554424286 |
| gaze_dev_std | 1.4497061967849731 | 0.15635009109973907 |
| head_yaw_dev | 1.7621599435806274 | 0.167064368724823 |
| head_pitch_dev | 2.145413398742676 | 0.208520770072937 |
| head_roll_mean | 2.5056116580963135 | 0.2519966959953308 |
| on_screen_ratio | 1.4758702516555786 | 0.15542763471603394 |
| off_screen_dwell_sec | 1.527828335762024 | 0.14926579594612122 |
| glance_count | 1.7756011486053467 | 0.17811259627342224 |
| blink_rate | 1.4667211771011353 | 0.1537388116121292 |
| perclos | 1.4877490997314453 | 0.15580856800079346 |
| face_present_ratio | 0.9341086149215698 | 0.09761041402816772 |
| body_motion_energy | 1.7350573539733887 | 0.16688957810401917 |
| hand_to_face_ratio | 1.2313156127929688 | 0.1309177726507187 |
| talking_score | 2.163098096847534 | 0.2314610332250595 |

Largest first-layer magnitudes: `head_roll_mean`, `talking_score`, `head_pitch_dev`. Live hard-zeros `talking_score` / blink / glance / perclos → those trained directions are unused live (**ISSUE**).

#### Train/serve pose baseline & window

| Check | Training | Live | Flag |
|---|---|---|---|
| Pose baseline | first 30 face frames / clip | first 8 session frames | **ISSUE** mismatch |
| Window | 2 s / 5 s MediaPipe windows | last 5 heartbeats (~10 s), approx features | **ISSUE** mismatch |

---

## Part 2: how the system works, traced with real numbers

### 2.1 Pipeline description (code)

| Step | Behaviour | Location |
|---|---|---|
| Browser capture | 224×224 canvas; `toDataURL('image/jpeg', 0.5)`; interval default **2000 ms**; skip tick if `inFlightRef` | `frontend/src/hooks/useMonitoringSession.js` L188–260, L9 |
| Heartbeat | `POST /api/session/<id>/heartbeat` with image + noise flags | same + `session.py` |
| Decode + face gate | Base64 JPEG decode; Haar `detectMultiScale` with `ML_FACE_*` (default upscale 1.0, minNeighbors 5, minSize 28, equalize false) | `ml_service.py` `_decode_frame`, `_detect_face`, L124–131 |
| No-face branch | MediaPipe pose landmarks; if person → `DISTRACTED` `body_no_face` conf 0.85; else `UNKNOWN` `no_face`. **No append** to fusion buffer | L984–1007 |
| M1 | Eye/face crop → MobileNetV2 softmax 4-class; if missing weights, heuristic defaults | `_infer_frame_signals` L779–812 |
| M2 | Face crop → yaw/pitch/roll; if missing, heuristic from box | L814–825 |
| M4 | Landmark buffer → 12 features → eng prob; fallback defaults if eng model missing / short buffer | `_score_window` L852–862; `compute_engagement_features` |
| Rolling buffer | deques maxlen **32**; score uses last `window_size` (default **5**) | L165–169, L1028–1035 |
| Fusion features (model5 order) | `p_*_mean`, `gaze_away_ratio=(l+r+d)/sum`, yaw/pitch/roll mean±std, `engagement_prob_mean` | `build_fusion_features` L623–646 |
| Fusion features (model6) | 14 names in `MODEL6_FEATURE_NAMES`; live approx L648–713 | same |
| Pose-baseline | Median yaw/pitch of first 8 face frames; subtract before fusion | `_update_pose_baseline`, `_centered_pose_buf` |
| Score | Standardise inside wrapper → MLP logit → sigmoid → `distract_prob`; compare pack/env threshold for `raw_fusion_verdict`; model6 then hysteresis | `_score_window` L878–915; `wrapper.py` |
| Episode / intervention | Duration bands, Tier 1 exception, pending lock, cooldown (unchanged design; see REPORT.md / intervention engine) | `intervention` services + `session.py` |
| observed_v1 | Focus = focused/(focused+distracted) observed seconds; coverage excludes UNKNOWN from numerator | `observation_coverage.py` |

**Current disk reality:** M1/M2/M4 missing → `ml_mode=partial` with fusion-only neural path + heuristic gaze/pose fillers (verified in prior shell `527310.txt`).

### 2.2 One real heartbeat traced end to end

CSV does **not** store the full model6 feature vector. Below: three heartbeats from Run 6 CSV `live_webcam_selftest_20261029T063746Z.csv` (session note in `selftest_metrics_run6.json`). **ISSUE:** every heartbeat in this CSV has `ml_mode=fallback` (103/103); no `inference_path=fusion` rows — live path was heuristic + body rule, not model6.

| Role | Phase / time | verdict | reason | inference_path | ml_mode | notes from CSV |
|---|---|---|---|---|---|---|
| FOCUSED reading | `read_1` @ ~2.13 s | FOCUSED | `heuristic_gate` | `heuristic` | fallback | face_box present; gaze_label=`center`; yaw≈5.22; `distract_prob` empty; `fusion_threshold`=0.5 |
| DISTRACTED phone | `phone` (first DISTRACTED ~4.26 s) | DISTRACTED | `body_no_face` | `body_no_face` | fallback | no fusion score; face absent → body rule |
| `body_no_face` / leave | `out_of_chair` UNKNOWN rows | UNKNOWN | `no_face` | `unusable` | fallback | 13/15 UNKNOWN; 2/15 FOCUSED (violates “no FOCUSED” design) |

---

## Part 3: expected behaviour vs current behaviour

### 3.1 Expected behaviour (design — code + thesis Tables 3.7 / 3.8 / 6.15)

| Situation | Face? | Body? | Expected M1 / pose / eng | Expected verdict source | Episode / interventions | Focus / coverage |
|---|---|---|---|---|---|---|
| Reading on screen | Yes | Yes | center / small yaw-pitch / high eng | FOCUSED via fusion | No distraction episode | Raises focus; counts covered |
| Looking down (notes/phone) | Often no / partial | Yes | down / pitch down | DISTRACTED (fusion or `body_no_face`) | Episode; Tier 1 ≤15 s then escalate | Distracted seconds |
| Head away | Often no | Yes | away / large \|yaw\| | DISTRACTED | Same | Distracted |
| Leave chair | No | No | n/a | UNKNOWN `no_face` | Close episode on UNKNOWN; no FOCUSED | Uncovered / unknown seconds |
| Face present, eyes off-screen | Yes | Yes | left/right/down | DISTRACTED via fusion | After hysteresis / duration bands | Distracted |
| Brief glance <5 s | Yes | Yes | brief away | Stay FOCUSED (model6 hysteresis enter needs 3 s ≥0.6) | No intervention | Focused |
| Poor lighting / partial face | Unreliable Haar | Maybe | unstable | UNKNOWN or body rule | Hold pending on UNKNOWN | Coverage drop |

### 3.2 Current behaviour (measured)

Source: Run 6 CSV `20261029T063746Z` + `raw/selftest_metrics_run6.json` (completed self-test; **not** the aborted Run 6b CSV `20261029T064541Z`).

| Situation | Measured so far | Match? | Likely cause |
|---|---|---|---|
| Reading on screen | read_1 27/29=93.1% FOCUSED; read_2 28/29=96.6% FOCUSED; 0 reading interventions | Yes (≥70% FOCUSED; ≤0.5 false/min) | Heuristic gate while face present (`ml_mode=fallback`) |
| Looking down (phone) | 9/15=60% DISTRACTED; first intervention 10.50 s Tier 1 | Partly (intervention ≤15 s Yes; DISTRACTED ≥70% **No**) | All 9 via `body_no_face`; 6/15 still FOCUSED |
| Head away | 13/15=86.7% DISTRACTED; first intervention 10.49 s Tier 1 | Yes | All 13 via `body_no_face` |
| Leave chair | 13/15=86.7% UNKNOWN; **2/15 FOCUSED** | Partly (≥70% UNKNOWN Yes; **no FOCUSED** No) | Brief face reacquire → heuristic FOCUSED |
| Face present, eyes off-screen / fusion | **0** DISTRACTED from fusion in phone+away (0/22) | No | Entire run `ml_mode=fallback`; fusion never used |
| Phone/away fusion share | Run 6 = **0.0** (0 of 22); Run 5 = 0 of 27 | No (target >50%) | Body-rule dominance; fusion not on live path this run |

---

## Part 4: live self-test (Run 6)

### Pre-conditions completed

| Step | Result |
|---|---|
| Tag | `thesis-final-v2` @ `2974633…` |
| DB backup | `evaluation/thesis_numbers/raw/FYP_LMS_backup_before_REPORT7.dump` length **127940** bytes; SHA-256 `113607FF7D14F74AE60CD2CF75AA1EC136FF0E8AF322C273CD0A3DC5CA2BB071` via `C:\Program Files\PostgreSQL\18\bin\pg_dump.exe -Fc …` |
| Threshold for Run 6 | Intended env **0.75** for Run 5 parity; **observed in CSV:** `fusion_threshold` blank on 38 rows and **0.5** on 65 rows; **`ml_mode=fallback` on all 103 rows** — model6 fusion **not** exercised live (**ISSUE**) |
| Live metrics | `raw/live_webcam_selftest_20261029T063746Z.csv` + `raw/selftest_metrics_run6.json` + console `raw/report7_live_selftest_console.txt` (session_id=103, module_id=9). Aborted later attempt `20261029T064541Z` / Run 6b **discarded** |

### Live metrics (Run 6 vs Run 5)

| Phase | Run 6 n | R6 FOCUSED | R6 DIST fusion | R6 DIST body | R6 UNKNOWN | Run 5 (same cols) |
|---|---|---|---|---|---|---|
| read_1 | 29 | 27 | 0 | 1 | 1 | 22 / 10 / 11 / 0 / 1 |
| phone | 15 | 6 | 0 | 9 | 0 | 15 / 2 / 0 / 13 / 0 |
| away | 15 | 2 | 0 | 13 | 0 | 15 / 1 / 0 / 14 / 0 |
| out_of_chair | 15 | 2 | 0 | 0 | 13 | 15 / 2 / 0 / 1 / 12 |
| read_2 | 29 | 28 | 0 | 0 | 1 | 30 / 24 / 4 / 1 / 1 |

| Metric | Run 6 | Flag vs Part 0.2 | Run 5 |
|---|---|---|---|
| read_1 % FOCUSED | 27/29 = 0.931 | **ABOVE EXPECTED** (≥0.70) | 10/22 ≈ 0.455 |
| read_2 % FOCUSED | 28/29 = 0.966 | **ABOVE EXPECTED** | 24/30 = 0.800 |
| false interventions / reading min | **0.0** (0 / 2.0 min) | **ABOVE EXPECTED** (≤0.5) | 1.0 (2 / 2.0 min) |
| phone % DISTRACTED | 9/15 = 0.600 | **BELOW EXPECTED** (≥0.70) | 13/15 ≈ 0.867 |
| away % DISTRACTED | 13/15 = 0.867 | **ABOVE EXPECTED** | 14/15 ≈ 0.933 |
| phone first intervention | 10.50 s Tier 1 | **AT EXPECTED** (≤15 s) | 12.36 s |
| away first intervention | 10.49 s Tier 1 | **AT EXPECTED** | 10.26 s |
| out_of_chair % UNKNOWN | 13/15 = 0.867 | **ABOVE EXPECTED** (≥0.70) | 12/15 = 0.800 |
| out_of_chair FOCUSED count | **2** | **ISSUE** (design: none) | 2 |
| phone+away fusion share of DISTRACTED | **0.0** (0/22) | **BELOW EXPECTED** (>0.50); same failure mode as Run 5 | 0/27 |
| reading face_box present share | 55/58 = 0.948 | — | 0.942 |
| Live path | `fallback` / heuristic + `body_no_face` only | **ISSUE** (model6 not used) | fusion false-alarms on reading + body on phone/away |

Interventions logged (4): phone Tier1+Tier2 and away Tier1+Tier2 — all `reason=body_no_face`. No reading-phase interventions.

---

## Part 5: cross-person video replay

**Not run.** No consented third-party recordings were supplied in this session; `agent_prompt_6_video_replay.md` was not present in the repo (glob 0 hits).

---

## Part 6: software checks

### pytest

Command:

```text
cd backend; ..\venvpy312\Scripts\python.exe -m pytest -q
```

Raw: `evaluation/thesis_numbers/raw/report7_pytest.txt`

```text
130 passed, 1226 warnings in 33.78s
EXIT:0
```

| Metric | Value | Flag |
|---|---|---|
| Passed | 130 | **AT EXPECTED** (reference 130) |
| Failed | 0 | **AT EXPECTED** |

### Heartbeat latency (Table 6.7 method)

Command: `evaluation/thesis_numbers/run_heartbeat_latency.py` with `ML_FUSION_THRESHOLD=0.75` after model6 `sys.path` fix. Raw: `raw/report7_latency_run_after_fix.txt` (+ `heartbeat_latency.json` from script). Warm-up `ml_mode=partial` both runs (M1/M2/M4 still missing — **NOT COMPARABLE** to thesis Table 6.7 full-inference 91.8 ms CUDA).

| Tag | n | median_ms | p95_ms | max_ms | ml_mode | Flag |
|---|---|---|---|---|---|---|
| CUDA (RTX 4050) | 50 | **61.00** | 100.84 | 226.19 | partial | **NOT COMPARABLE** (partial ≠ full); still ≪ 2000 ms |
| CPU (`CUDA` disabled) | 50 | **38.95** | 62.44 | 72.71 | partial | **NOT COMPARABLE**; ≪ 2000 ms |

Warm-up heartbeat: CUDA 7472 ms (cold), CPU 421 ms. All 50 timed heartbeats HTTP 200 / face detected on both tags.

---

## Part 7: summary for the thesis

### Numbers table (complete so far)

| Number | Value | Flag | Section |
|---|---|---|---|
| Tag / commit | `thesis-final-v2` / `2974633d05e35e5e54f9cf6654809b5df13d2a9c` | — | 0.1 |
| M1 accuracy / macro-F1 (new) | Not measured | ISSUE | 1 |
| M2 MAE (new) | Not measured | ISSUE | 1 |
| M4 metrics (new) | Not measured | ISSUE | 1 |
| M5 original / blocked / ablations (new) | Not measured | ISSUE / NOT COMPARABLE | 1 |
| M6 LOSO mean macro-F1 | 0.7510756185532369 | ABOVE EXPECTED (≥0.70) | 1 / 0.1 |
| M6 LOSO mean F1+ | 0.5691967661861222 | ABOVE EXPECTED vs honest 0.54 | 1 |
| M6 LOSO mean ROC-AUC | 0.9456062223613726 | ABOVE EXPECTED vs 0.77 | 1 |
| M6 S01/S02/S03 macro-F1 | 0.957… / 0.642… / 0.653… | ABOVE / BELOW / BELOW | 1 |
| M6 pack threshold | 0.48000000000000004 | ISSUE (chosen via test-fold mean) | 0.1 |
| pytest | 130 passed | AT EXPECTED | 6 |
| Run 6 live metrics | see Part 4 (`20261029T063746Z`) | mixed; **ISSUE** `ml_mode=fallback` | 4 |
| R6 reading FOCUSED | 0.931 / 0.966 | ABOVE EXPECTED | 4 |
| R6 false interv. / reading min | 0.0 | ABOVE EXPECTED (≤0.5) | 4 |
| R6 phone / away % DIST | 0.600 / 0.867 | BELOW / ABOVE | 4 |
| R6 phone+away fusion share | 0.0 (0/22) | BELOW EXPECTED (>0.50) | 4 |
| Latency CUDA/CPU median | 61.00 / 38.95 ms (`partial`) | NOT COMPARABLE vs 91.8 full | 6 |
| Video replay | Not run | — | 5 |
| DB backup size | 127940 bytes | — | 4 |

### Every ISSUE found

1. **M1/M2/M4/M5 checkpoint files missing on disk** — cannot re-measure or run `ml_mode=full`. Evidence: `Test-Path` False; load warnings in terminal `527310.txt`.
2. **Model6 thresholds picked on LOSO test subjects** (`_pick_threshold(yte, proba)`). Evidence: `train.py` L233–234, L336–337.
3. **Model6 labels from feature rules / distraction_proxy on model inputs**. Evidence: `windows.py` `label_window_row` / `relabel_dataframe`.
4. **Train/serve mismatch** — training MediaPipe 2/5 s windows + blink/glance/talk features; live 5-heartbeat approx with several features zeroed; baseline 30 vs 8 frames. Evidence: `windows.py`, `ml_service.py` L648–713, L135–138.
5. **S02 only 10 distracted labeled windows** (<30). Evidence: windows crosstab.
6. **Historical M5 Acc 1.0** remains leakage/not a clean reference for honesty (REPORT.md) — still listed as Table 6.10 reference with ISSUE inheritance.
7. **Run 6 live path never used model6** — CSV `ml_mode=fallback` on 103/103 heartbeats; `inference_path` only `heuristic` / `body_no_face` / `unusable`; observed `fusion_threshold` 0.5 (not env 0.75). Offline LOSO gains **do not** transfer in this live measurement.
8. **Phone phase 60% DISTRACTED** below ≥70% target; **out_of_chair still has 2 FOCUSED** heartbeats (design: none).
9. **Phone+away fusion share still 0.0** (0/22), same as Run 5 body-rule dominance (and here fusion was absent entirely).

### What improved, what got worse, what did not change

- **Improved (offline):** Participant-independent mean macro-F1 for the new fusion (model6 LOSO mean **0.751…**) is above the ≥0.70 target; mean ROC-AUC **0.945…** beats the honest 0.77 baseline file constants.
- **Improved (live vs Run 5, same participant protocol):** Reading FOCUSED rose to **93–97%**; **false interventions dropped from 1.0 → 0.0** per reading minute (Run 5 had fusion false-alarms on `read_1`).
- **Got worse / risk:** Live Run 6 did **not** exercise model6 (`fallback` only). Phone detection **fell** to 60% DISTRACTED (was ~87% in Run 5). Offline LOSO gains remain unproven live.
- **Did not change:** Backend pytest still **130 passed**. Phone/away DISTRACTED still 100% `body_no_face`. M1–M5 checkpoints still missing on disk.

### Not done / not measured

- Fresh M1/M2/M4/M5 evaluation and old-vs-new on the same test sets (missing checkpoints).
- M5 original/blocked/ablation re-fits; model6 gaze/head/eng-style ablations.
- A live self-test with confirmed `ml_mode=partial` / `fusion_kind=model6_mlp` and frozen `ML_FUSION_THRESHOLD` (path-fix restart happened **after** the completed Run 6 CSV).
- Part 5 video replay.
- A live self-test with confirmed `ml_mode=partial` / model6 on the webcam protocol (latency harness used partial; completed Run 6 CSV did not).
- Application code: crash/path hotfix to `ml_service.py` sys.path (repo root for model6 unpickle) recorded after Run 6; **not** present in the completed Run 6 process.

---

*Report status: Part 0 locked; Parts 1/3.2/4 (Run 6 CSV) / 5 (not run) / 6 (pytest + partial latency) recorded; fusion-on webcam re-run still pending.*
