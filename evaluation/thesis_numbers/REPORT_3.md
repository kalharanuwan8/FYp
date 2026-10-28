# REPORT_3 — Reviewer metrics, deployed config, escalation fix, security, Run 5

Local run only. No invented numbers. Branch: `expert-remediation`.  
Python: `venvpy312\Scripts\python.exe`. Live DB: PostgreSQL `FYP_LMS`. Pytest: in-memory SQLite.

---

## Exact commands run

```text
# DB backup (before code changes)
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -h localhost -U postgres -d FYP_LMS -F c `
  -f evaluation\thesis_numbers\raw\FYP_LMS_backup_20261028_113755.dump
# Also present: FYP_LMS_backup_20261028_REPORT3.dump (122530 bytes)

cd backend
..\venvpy312\Scripts\python.exe -m pytest --tb=line -q
# baseline before edits: 118 passed

..\venvpy312\Scripts\python.exe evaluation\thesis_numbers\selftest_metrics.py
# Wrote evaluation\thesis_numbers\raw\selftest_metrics.json

..\venvpy312\Scripts\python.exe evaluation\thesis_numbers\run_intervention_v2.py
# Wrote evaluation\thesis_numbers\raw\intervention_v2.json
# (run_intervention.py also re-run after the fix → raw\intervention.json matches v2 sequences)

cd backend
..\venvpy312\Scripts\python.exe -m pytest tests\test_intervention_escalation.py -q
# 7 passed

..\venvpy312\Scripts\python.exe -m pytest tests\test_security_access.py -q
# 4 passed

..\venvpy312\Scripts\python.exe -m pytest --tb=line -q
# 129 passed, 1226 warnings

# Frozen backend for Run 5
$env:ML_FUSION_THRESHOLD="0.75"
..\venvpy312\Scripts\python.exe wsgi.py

$env:THESIS_API="http://127.0.0.1:5000"
$env:THESIS_EMAIL="student@luma.com"
$env:THESIS_PASSWORD="Student123!"
$env:THESIS_MODULE_ID="2"
.\venvpy312\Scripts\python.exe evaluation\thesis_numbers\live_webcam_selftest.py
# CSV: live_webcam_selftest_20261028T063352Z.csv  session_id=94
```

---

## Files changed

- `backend/app/services/intervention_engine.py` — Tier 1 ambient: no pending/cooldown; one per episode
- `backend/tests/test_intervention_engine.py` — 2 legacy tests retargeted 8 s → 12 s (Tier 2 pending path)
- `backend/tests/test_phase2a_observation.py` — 1 legacy test retargeted 8 s → 12 s
- `backend/tests/test_intervention_escalation.py` — **new** (7 tests)
- `backend/app/config.py` — JWT query-string for authenticated file URLs
- `backend/app/__init__.py` — public `/uploads/<file>` returns 401
- `backend/app/db_models/course.py` — `reveal_milestone_answers` / `reveal_answer`
- `backend/app/routes/courses.py` — `GET /materials/<id>/file`; strip answers for students
- `backend/app/routes/quizzes.py` — ownership/enrolment on quiz reads / attempts list
- `backend/tests/test_security_access.py` — **new** (4 tests)
- `frontend/src/pages/student/SubjectDetail.jsx` — authenticated media URL
- `frontend/src/components/student/VideoLearningPlayer.jsx` — authenticated media URL
- `frontend/src/pages/student/QuizAttempt.jsx` — authenticated remediation open
- `evaluation/thesis_numbers/selftest_metrics.py` — **new**
- `evaluation/thesis_numbers/run_intervention_v2.py` — post-fix simulation
- `evaluation/thesis_numbers/raw/*` — dumps, metrics JSON, intervention JSON, Run 5 CSV
- This file

---

## Part 1 — Self-test metrics (Runs 2 / 3 / 4)

Source: `raw/selftest_metrics.json`.

| Run | session | CSV |
| --- | --- | --- |
| Run 2 | 85 | `raw/live_webcam_selftest_20261028T031728Z.csv` |
| Run 3 | 91 | `raw/live_webcam_selftest_20261028T041833Z.csv` |
| Run 4 | 93 | `raw/live_webcam_selftest_20261028T050110Z.csv` |

**Source rules:**

- `distracted_fusion` — DISTRACTED with `inference_path` in `{fusion, heuristic}`
- `distracted_body_no_face` — DISTRACTED with `reason`/`inference_path` = `body_no_face`
- `distracted_undifferentiated` — DISTRACTED on Run 2 (no `inference_path` column); counted as face-based for coverage
- UNKNOWN reasons from the `reason` column

### Verdict counts by source

#### Run 2 (session 85)

*Limitation:* no `inference_path`; DISTRACTED cannot be split into fusion vs other face-based sources.

| phase | n | FOCUSED | DIST fusion | DIST body_no_face | DIST undifferentiated | UNKNOWN (reasons) |
| --- | --- | --- | --- | --- | --- | --- |
| read_1 | 30 | 15 | 0 | 0 | 2 | 13 (`no_face`×13) |
| phone | 15 | 4 | 0 | 0 | 0 | 11 (`no_face`×11) |
| away | 15 | 0 | 0 | 0 | 1 | 14 (`no_face`×14) |
| out_of_chair | 15 | 0 | 0 | 0 | 2 | 13 (`no_face`×13) |
| read_2 | 30 | 6 | 0 | 0 | 23 | 1 (`no_face`×1) |

#### Run 3 (session 91)

| phase | n | FOCUSED | DIST fusion | DIST body_no_face | UNKNOWN (reasons) |
| --- | --- | --- | --- | --- | --- |
| read_1 | 30 | 0 | 28 | 0 | 2 (`no_face`×2) |
| phone | 15 | 0 | 2 | 0 | 13 (`no_face`×13) |
| away | 15 | 0 | 2 | 0 | 13 (`no_face`×13) |
| out_of_chair | 15 | 0 | 0 | 0 | 15 (`no_face`×15) |
| read_2 | 30 | 4 | 20 | 0 | 6 (`no_face`×6) |

#### Run 4 (session 93)

| phase | n | FOCUSED | DIST fusion | DIST body_no_face | UNKNOWN (reasons) |
| --- | --- | --- | --- | --- | --- |
| read_1 | 30 | 10 | 9 | 11 | 0 |
| phone | 15 | 2 | 0 | 13 | 0 |
| away | 15 | 0 | 3 | 10 | 2 (`no_face`×2) |
| out_of_chair | 15 | 0 | 0 | 4 | 11 (`no_face`×11) |
| read_2 | 30 | 17 | 11 | 1 | 1 (`no_face`×1) |

### Coverage per phase

Face-based = FOCUSED + fusion DISTRACTED (+ undifferentiated on Run 2). Incl. body = face-based + `body_no_face`.

| run | phase | coverage_face_based | coverage_incl_body_no_face |
| --- | --- | --- | --- |
| Run 2 | read_1 | 0.5667 | 0.5667 |
| Run 2 | phone | 0.2667 | 0.2667 |
| Run 2 | away | 0.0667 | 0.0667 |
| Run 2 | out_of_chair | 0.1333 | 0.1333 |
| Run 2 | read_2 | 0.9667 | 0.9667 |
| Run 3 | read_1 | 0.9333 | 0.9333 |
| Run 3 | phone | 0.1333 | 0.1333 |
| Run 3 | away | 0.1333 | 0.1333 |
| Run 3 | out_of_chair | 0.0 | 0.0 |
| Run 3 | read_2 | 0.8 | 0.8 |
| Run 4 | read_1 | 0.6333 | 1.0 |
| Run 4 | phone | 0.1333 | 1.0 |
| Run 4 | away | 0.2 | 0.8667 |
| Run 4 | out_of_chair | 0.0 | 0.2667 |
| Run 4 | read_2 | 0.9333 | 0.9667 |

### Detection delay (phone / away)

| run | phase | first DIST any | first DIST fusion/undiff | first DIST body_no_face | first intervention (tier) |
| --- | --- | --- | --- | --- | --- |
| Run 2 | phone | none | none | none | none |
| Run 2 | away | 24.515 | 24.515 | none | none |
| Run 3 | phone | 2.150 | 2.150 | none | none |
| Run 3 | away | 8.305 | 8.305 | none | none |
| Run 4 | phone | 0.101 | none | 0.101 | 12.514 (tier 1) |
| Run 4 | away | 0.100 | 0.100 | 6.219 | none |

### Interventions

| run | timestamp_utc | phase | seconds_into_phase | tier | type | verdict source |
| --- | --- | --- | --- | --- | --- | --- |
| Run 2 | 2026-10-28T03:16:45.776743+00:00 | read_2 | 22.626 | 1 | ambient_cue | distracted_undifferentiated |
| Run 3 | 2026-10-28T04:14:48.014747+00:00 | read_1 | 8.177 | 1 | ambient_cue | distracted_fusion |
| Run 3 | 2026-10-28T04:18:07.136104+00:00 | read_2 | 37.017 | 1 | ambient_cue | distracted_fusion |
| Run 4 | 2026-10-28T04:57:53.876408+00:00 | read_1 | 38.852 | 1 | ambient_cue | distracted_fusion |
| Run 4 | 2026-10-28T04:58:32.604673+00:00 | phone | 12.514 | 1 | ambient_cue | distracted_body_no_face |
| Run 4 | 2026-10-28T05:00:56.613161+00:00 | read_2 | 51.277 | 1 | ambient_cue | distracted_fusion |

### False interventions per study minute (reading ÷ 2.0 min)

| run | n reading interventions | reading minutes | false interventions / study minute |
| --- | --- | --- | --- |
| Run 2 | 1 | 2.0 | 0.5 |
| Run 3 | 2 | 2.0 | 1.0 |
| Run 4 | 2 | 2.0 | 1.0 |

### Face detected during reading (`read_1`+`read_2`)

| run | face_true | face_false | share of n |
| --- | --- | --- | --- |
| Run 2 | 46 | 14 | 0.7667 |
| Run 3 | 52 | 8 | 0.8667 |
| Run 4 | 47 | 13 | 0.7833 |

### observed_v1 session summaries (FYP_LMS)

| session_id | focus_metric_version | focus % | coverage % | T_F (s) | T_D (s) | T_U (s) | ended_at |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 85 | observed_v1 | 46.809988151073135 | 38.85204036250304 | 51.18948698043823 | 58.16641974449158 | 172.1116962750702 | 2026-10-28T03:17:28.403589 |
| 91 | observed_v1 | 7.06039220888751 | 37.09924177368838 | 8.231949090957642 | 108.36141920089722 | 197.68089370814516 | 2026-10-28T04:18:33.431674 |
| 93 | observed_v1 | 31.161904248355583 | 79.00505448337819 | 59.16362643241882 | 130.69520235061646 | 50.45342721696471 | 2026-10-28T05:01:10.477198 |

---

## Part 2 — Exact deployed configuration (Run 4)

| item | value | evidence |
| --- | --- | --- |
| Heartbeat interval | **2000 ms** | `useMonitoringSession.js` `intervalMs=2000`; self-test `INTERVAL_S=2.0` |
| JPEG size | **224×224** | frontend canvas; self-test resize |
| JPEG quality | **0.5** | `toDataURL('image/jpeg', 0.5)`; self-test JPEG quality 50 |
| `ML_WINDOW_FRAMES` | **3** (env unset) | `ml_service.py` default |
| Face upscale | **1.0** | `ML_FACE_UPSCALE` default (`ms28_n5`) |
| Face min neighbours | **5** | `ML_FACE_MIN_NEIGHBORS` default |
| Face min size | **28** | `ML_FACE_MIN_SIZE` default |
| Face equalise | **false** | `ML_FACE_EQUALIZE` default |
| Eye crop | Haar eyes in face; else top half of face gray | `_infer_frame_signals` |
| Face crop padding | **15%** of face width | `pad = int(fw * 0.15)` |
| M1 gaze input | eye crop → resize to checkpoint `img_size` (**96**) | gaze `best.pt` `img_size=96`, epoch 15 |
| M2 pose input | RGB face crop **224×224** | `pose_tf` |
| Engagement min-obs | if **&lt;4** valid landmark frames → default feature vector | `compute_engagement_features` |
| Live 3-frame buffer | score from ≥1 face frame; trim to last 3 | `predict_frame_image` |
| Pose baseline | first **8** face-present frames; **median** yaw/pitch; subtract before fusion | `ML_POSE_BASELINE_FRAMES`; `_update_pose_baseline` |
| Fusion threshold | **0.75 from env** `ML_FUSION_THRESHOLD`; package stores **0.5** | Run 4 CSV; `joblib` package |
| `body_no_face` | no Haar face + MediaPipe person → DISTRACTED; not buffered | `predict_frame_image` |
| Cooldown | **30.0 s** | `_get_cooldown_seconds` / engine default |
| Tier bands | &lt;5→0; &lt;10→1; &lt;20→2; &lt;40→3; else 4 | `distraction_level_from_duration` |

### Checkpoints (re-hashed)

| file | sha256 | bytes | epoch |
| --- | --- | --- | --- |
| `model1_gaze/best.pt` | `8127a926…2eba32` | 27089538 | 15 |
| `model2_pose/best.pt` | `a9116270…0f629` | 134253858 | 3 |
| `model4_engagement/model.pkl` | `d39b5f16…beb237e9` | 2419 | n/a |
| `model5_fusion/model.pkl` | `b465e0c4…42020e6` | 1853 | n/a (threshold 0.5) |

Full digests: `raw/checkpoint_hashes_verified.json`.

### Fusion training used pose-baseline subtraction?

**No.** `models/src/model5_fusion/prep.py` / `prepare.py` use raw `yaw_mean`/`pitch_mean` with no session median subtraction. Baseline exists only in live `ml_service.py` (“No retrain”).

---

## Part 3 — Intervention escalation fix

### Fix

In `intervention_engine.py`:

1. Tier 1 `ambient_cue` does **not** set `_pending_intervention` and does **not** update `last_intervention_at`.
2. At most one ambient cue per episode (`_ambient_episode_key`); cleared on FOCUSED reset.
3. Tiers 2–4 keep pending lock + 30 s cooldown.
4. Ambient still returned to the route → still logged in `InterventionLog`.

Legacy tests that asserted pending after an 8 s (Tier 1) episode were retargeted to **12 s (Tier 2)** intentionally.

### Simulation (wall-clock base `1_700_000_000`)

From `raw/intervention_v2.json` / post-fix `raw/intervention.json`:

#### Before (REPORT.md §9 / pre-fix `intervention.json` snapshot)

| second | tier | type |
| --- | --- | --- |
| 6 | 1 | ambient_cue |

(only; pending blocked Tier 2)

#### After — no response

| second | tier | type |
| --- | --- | --- |
| 6 | 1 | ambient_cue |
| 10 | 2 | pacing_pause |

#### After — `ignored` 2 s after each Tier 2–4

| second | tier | type |
| --- | --- | --- |
| 6 | 1 | ambient_cue |
| 10 | 2 | pacing_pause |
| 40 | 4 | content_pacing_reduction |
| 70 | 4 | suggest_break |
| 100 | 4 | suggest_break |

#### After — `reengaged` 2 s after each Tier 2–4

| second | tier | type |
| --- | --- | --- |
| 6 | 1 | ambient_cue |
| 10 | 2 | pacing_pause |
| 40 | 4 | content_pacing_reduction |
| 70 | 4 | suggest_break |
| 100 | 4 | suggest_break |

#### `enabled_tiers=[3,4]` at 6 s

Fired: **none**.

### Pytest

- Escalation file: **7 passed**
- Full suite after Parts 3–4: **129 passed**, 1226 warnings

---

## Part 4 — Security

### Fixed

1. **Public uploads blocked.** `/uploads/<filename>` → **401**. Serve via `GET /api/courses/materials/<id>/file` (JWT header or `?token=`), checking enrolled student / owning teacher / admin.
2. **Quiz reads.** Non-owner teachers and non-enrolled students get **403** on module quiz list, quiz detail, and attempts list.
3. **Milestone answers.** Student (and non-owner teacher) subject detail omits `correct_option`.

### Tests

`tests/test_security_access.py` — **4 passed**.

### Frontend

`SubjectDetail`, `VideoLearningPlayer`, and remediation open in `QuizAttempt` use the authenticated material URL.

---

## Part 5 — Run 5 confirmation self-test

**Label:** Run 5: frozen settings, post-escalation fix, same participant

- CSV: `raw/live_webcam_selftest_20261028T063352Z.csv`
- `session_id=94`
- Metrics: `raw/selftest_metrics_run5.json`
- Backend: `ML_FUSION_THRESHOLD=0.75`, no further code changes after start
- Note: `read_1` logged **22** heartbeats (reported as observed; not re-run)

### Per-phase table (script stdout)

| phase | n | focused | distracted | unknown | sec to first DISTRACTED | sec to first intervention | first tier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| read_1 | 22 | 10/22 = 0.4545 | 11/22 = 0.5 | 1/22 = 0.0455 | 26.911 | 43.341 | 1 |
| phone | 15 | 2/15 = 0.1333 | 13/15 = 0.8667 | 0 | 4.190 | 12.361 | 1 |
| away | 15 | 1/15 = 0.0667 | 14/15 = 0.9333 | 0 | 0.101 | 10.256 | 1 |
| out_of_chair | 15 | 2/15 = 0.1333 | 1/15 = 0.0667 | 12/15 = 0.8 | 0.101 | none | none |
| read_2 | 30 | 24/30 = 0.8 | 5/30 = 0.1667 | 1/30 = 0.0333 | 2.169 | none | none |

### Part 1 metrics (Run 5)

#### Verdict counts

| phase | n | FOCUSED | DIST fusion | DIST body_no_face | UNKNOWN |
| --- | --- | --- | --- | --- | --- |
| read_1 | 22 | 10 | 11 | 0 | no_face=1 |
| phone | 15 | 2 | 0 | 13 | 0 |
| away | 15 | 1 | 0 | 14 | 0 |
| out_of_chair | 15 | 2 | 0 | 1 | no_face=12 |
| read_2 | 30 | 24 | 4 | 1 | no_face=1 |

#### Coverage

| phase | face_model | + body_no_face |
| --- | --- | --- |
| read_1 | 0.9545 | 0.9545 |
| phone | 0.1333 | 1.0 |
| away | 0.0667 | 1.0 |
| out_of_chair | 0.1333 | 0.2 |
| read_2 | 0.9333 | 0.9667 |

#### Detection delay

| phase | first any | first fusion | first body_no_face | first intervention |
| --- | --- | --- | --- | --- |
| phone | 4.190 | none | 4.190 | 12.361 tier=1 |
| away | 0.101 | none | 0.101 | 10.256 tier=1 |

#### Interventions (live Tier 2 after ambient — escalation fix confirmed)

| timestamp_utc | sec into phase | phase | tier | type | source |
| --- | --- | --- | --- | --- | --- |
| 2026-10-28T06:30:41.479592+00:00 | 43.341 | read_1 | 1 | ambient_cue | distracted_fusion |
| 2026-10-28T06:30:45.527992+00:00 | 47.390 | read_1 | 2 | pacing_pause | distracted_fusion |
| 2026-10-28T06:31:15.755257+00:00 | 12.361 | phone | 1 | ambient_cue | distracted_body_no_face |
| 2026-10-28T06:31:17.790898+00:00 | 14.396 | phone | 2 | pacing_pause | distracted_body_no_face |
| 2026-10-28T06:31:48.742201+00:00 | 10.256 | away | 1 | ambient_cue | distracted_body_no_face |
| 2026-10-28T06:31:52.857198+00:00 | 14.371 | away | 2 | pacing_pause | distracted_body_no_face |

False interventions / study minute: **1.0** (2 reading interventions / 2.0)  
Face detected during reading: **49/52 = 0.9423**

#### observed_v1 session 94

| session_id | version | focus % | coverage % | T_F | T_D | T_U | ended_at |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 94 | observed_v1 | 46.91830345147059 | 58.40542339214008 | 82.044597864151 | 92.82233428955078 | 124.53494184629824 | 2026-10-28T06:33:51.603576 |

---

## Not done

- Nothing required by Parts 1–5 remains incomplete for this report.
- No model checkpoint was retrained or overwritten.
- Face gate defaults, live `ML_FUSION_THRESHOLD=0.75`, pose baseline, remediation, and analytics were not redesigned beyond the escalation and security fixes listed above.
- Run 5 `read_1` had 22 heartbeats; reported as observed, not re-run.
