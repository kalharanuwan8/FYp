# REPORT_2 — Adaptive quiz remediation and developer webcam self-test

Local run only. No estimated numbers.

## Thesis description (plain sentences)

After a student finishes a quiz that belongs to a video lesson, the system checks how many answers were wrong. If more than half are wrong, it does not only suggest replaying the same video. It looks up the student’s latest sealed monitoring summary for that module (coverage and focus already stored as observed_v1). High coverage with high focus is treated as a likely comprehension problem and a different format is offered first; high coverage with lower focus is treated as a likely attention problem and a guided re-watch is offered, with a different format as an option when one exists. Missing or low-coverage monitoring defaults to the different-format path. Different-format content is chosen only from what already exists: a teacher-uploaded document or other material, else a teacher-saved summary plus milestone questions, else a guided re-watch of the video with those checkpoints listed. Unapproved LLM drafts are never shown, and Ollama is not required at quiz time. The choice and path are stored in a RemediationEvent row, and the student sees a calm card titled “Let’s try this another way.”

## Design decisions

- Trigger thresholds (`REMEDIATION_ERROR_RATE_THRESHOLD=0.50`, `REMEDIATION_COVERAGE_MIN_PCT=50.0`, `REMEDIATION_FOCUS_MIN_PCT=70.0`) are engineering parameters in `backend/app/config.py`, not clinical thresholds. Error rate must be **strictly greater than** 50% to trigger.
- Session lookup uses the stored observed_v1 snapshot only (no recomputation from heartbeats). The open quiz monitoring session is not used as the behaviour record for the decision.
- Guided re-watch does not invent video cut timestamps (`content_position_seconds` is never written in this codebase). The card lists the existing video and active milestone questions as checkpoints between parts.
- Live app database is PostgreSQL `FYP_LMS` (from `backend/.env`). Pytest uses in-memory SQLite. Intervention tiers, cooldowns, analytics, rewards, and model checkpoints were not changed.

## Files changed

- `backend/app/config.py` — remediation engineering parameters
- `backend/app/db_models/remediation.py` — `RemediationEvent` model (new)
- `backend/app/db_models/__init__.py` — export model
- `backend/app/__init__.py` — import remediation module for `create_all`
- `backend/app/services/remediation_service.py` — decision + content selection (new)
- `backend/app/routes/quizzes.py` — remediation on submit + choice endpoint
- `backend/tests/test_remediation.py` — unit + API tests (new)
- `frontend/src/services/quizService.js` — `recordRemediationChoice`
- `frontend/src/pages/student/QuizAttempt.jsx` — remediation card UI
- `evaluation/thesis_numbers/remediation_card.png` — manual screenshot
- `evaluation/thesis_numbers/raw/FYP_LMS_backup_20261028_082536.dump` — DB backup before edits
- Git branch: `expert-remediation`

## Exact commands run

```text
git checkout -b expert-remediation
pg_dump ... -d FYP_LMS -F c -f evaluation\thesis_numbers\raw\FYP_LMS_backup_20261028_082536.dump

cd backend
..\venvpy312\Scripts\python.exe -m pytest tests\test_remediation.py -v --tb=short
..\venvpy312\Scripts\python.exe -m pytest --tb=line

..\venvpy312\Scripts\python.exe wsgi.py
cd frontend && npm run dev

# Manual: login student@luma.com, fail quiz 1 (module 2), screenshot remediation card

$env:THESIS_API="http://127.0.0.1:5000"
$env:THESIS_EMAIL="student@luma.com"
$env:THESIS_PASSWORD="Student123!"
$env:THESIS_MODULE_ID="2"
.\venvpy312\Scripts\python.exe evaluation\thesis_numbers\live_webcam_selftest.py
```

## Test results (pytest)

Full suite from `backend`:

```text
collected 109 items
================ 109 passed, 1134 warnings in 71.93s (0:01:11) ================
```

Remediation file alone: **10 passed** in 3.38s. Prior suite behaviour remained green; new remediation tests are included in the 109 total.

## Manual remediation check

- Student: `student@luma.com` / `Student123!` (guardian consent already recorded)
- Enrolled subject 3 for that student so module 2 was reachable
- Quiz: id `1`, module id `2` (“Introduction To Database” / “Database Design”)
- Score shown: 0% (0/1 correct) → remediation card offered approved pack (“Read the explanation — Database Design”)
- Screenshot: `evaluation/thesis_numbers/remediation_card.png`
- Backend ML load check: `ml_mode=full` (gaze, pose, engagement, fusion checkpoints loaded)

## Developer self-test, single participant

Credentials used: `student@luma.com` / `Student123!`, `THESIS_MODULE_ID=2`, API `http://127.0.0.1:5000`.

### First run (20261028T031104Z) — incomplete heartbeats after phone

CSV: `evaluation/thesis_numbers/raw/live_webcam_selftest_20261028T031104Z.csv`  
`session_id=84`

| phase | n_heartbeats | focused | distracted | unknown | seconds_to_first_distracted | seconds_to_first_intervention | first_intervention_tier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| read_1 | 30 | 7/30 = 0.233… | 12/30 = 0.4 | 11/30 = 0.367… | 10.293… | 43.016… | 1 |
| phone | 3 | 0/3 = 0.0 | 3/3 = 1.0 | 0/3 = 0.0 | 0.101… | none | none |
| away | 0 | n=0 | n=0 | n=0 | none | none | none |
| out_of_chair | 0 | n=0 | n=0 | n=0 | none | none | none |
| read_2 | 0 | n=0 | n=0 | n=0 | none | none | none |

### Second run (re-test on request, 20261028T031728Z)

CSV: `evaluation/thesis_numbers/raw/live_webcam_selftest_20261028T031728Z.csv`  
`session_id=85`

| phase | n_heartbeats | focused | distracted | unknown | seconds_to_first_distracted | seconds_to_first_intervention | first_intervention_tier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| read_1 | 30 | 15/30 = 0.5 | 2/30 = 0.0667… | 13/30 = 0.433… | 2.079… | none | none |
| phone | 15 | 4/15 = 0.267… | 0/15 = 0.0 | 11/15 = 0.733… | none | none | none |
| away | 15 | 0/15 = 0.0 | 1/15 = 0.0667… | 14/15 = 0.933… | 24.515… | none | none |
| out_of_chair | 15 | 0/15 = 0.0 | 2/15 = 0.133… | 13/15 = 0.867… | 0.102… | none | none |
| read_2 | 30 | 6/30 = 0.2 | 23/30 = 0.767… | 1/30 = 0.0333… | 2.140… | 22.626… | 1 |

Numbers above are copied from the script printout; nothing was smoothed.

## Face-gate fix (after the second self-test)

**Problem.** Every UNKNOWN in the second self-test had `reason=no_face`, including many reading frames. Haar used `minSize=(50, 50)` on 224×224 JPEGs. Offline BIWI (REPORT.md §6) found a face in only 16/1314 near-frontal frames with that call.

**Change.** Shared `_detect_face` in `backend/app/services/ml_service.py`; no-face frames are not appended to the fusion window; heartbeat adds a `diagnostics` object; self-test CSV gains diagnostic columns.

**Offline choice** (`evaluation/thesis_numbers/raw/face_gate_check.json`): settings `ms28_n5` — `ML_FACE_UPSCALE=1.0`, `ML_FACE_MIN_NEIGHBORS=5`, `ML_FACE_MIN_SIZE=28`, equalize off. BIWI 0–15° face-found ratio **0.426** (was **0.012**); person-present natural+focused ratio unchanged at **0.308**; empty-frame control **0** faces.

**JSON bug found on first post-fix live run** (`20261028T040908Z`): when a face *was* found, `face_box_px` held NumPy `int32` values and Flask returned HTTP **500** (38/105 heartbeats). Fixed by casting boxes to plain `int`. That broken run is not used as a behaviour table.

**Pytest after face-gate work:** `112 passed, 1134 warnings in 36.31s` (includes `tests/test_face_gate.py`).

### Third developer self-test (after face-gate + JSON fix), `20261028T041833Z`

CSV: `evaluation/thesis_numbers/raw/live_webcam_selftest_20261028T041833Z.csv`  
`session_id=91` — all **105** heartbeats HTTP 200.

| phase | n_heartbeats | focused | distracted | unknown | seconds_to_first_distracted | seconds_to_first_intervention | first_intervention_tier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| read_1 | 30 | 0/30 = 0.0 | 28/30 ≈ 0.933 | 2/30 ≈ 0.067 | 2.084… | 8.177… | 1 |
| phone | 15 | 0/15 = 0.0 | 2/15 ≈ 0.133 | 13/15 ≈ 0.867 | 2.150… | none | none |
| away | 15 | 0/15 = 0.0 | 2/15 ≈ 0.133 | 13/15 ≈ 0.867 | 8.305… | none | none |
| out_of_chair | 15 | 0/15 = 0.0 | 0/15 = 0.0 | 15/15 = 1.0 | none | none | none |
| read_2 | 30 | 4/30 ≈ 0.133 | 20/30 ≈ 0.667 | 6/30 = 0.2 | 10.336… | 37.017… | 1 |

Compared with the second run: UNKNOWN while reading dropped sharply (43% → 7% on read_1), so the face gate helped presence. Away / out-of-chair remain mostly UNKNOWN as designed. Phone is still mostly UNKNOWN, not DISTRACTED. Reading phases are now dominated by DISTRACTED (false alarms), including Tier 1 cues — fusion/false-positive behaviour, not a face-miss problem.

Extra files from this fix: `backend/app/services/ml_service.py`, `backend/app/routes/session.py` (diagnostics), `backend/tests/test_face_gate.py`, `evaluation/thesis_numbers/run_face_gate_check.py`, `evaluation/thesis_numbers/raw/face_gate_check.json`.

## S3 runtime changes (no checkpoint retrain)

- Env `ML_FUSION_THRESHOLD` override (live run used **0.75**).
- Per-session pose baseline: median yaw/pitch of first 8 face-present frames, subtracted before fusion.
- No Haar face + MediaPipe person → `DISTRACTED` / `reason=body_no_face` (not appended to fusion buffer).
- Pytest: **118 passed** (includes `tests/test_s3_fusion_runtime.py`).

### Fourth developer self-test (after S3), `20261028T050110Z`

CSV: `evaluation/thesis_numbers/raw/live_webcam_selftest_20261028T050110Z.csv`  
`session_id=93` — **105** heartbeats. `fusion_threshold=0.75`. Pose baseline locked on 45 face-present rows.

| phase | n_heartbeats | focused | distracted | unknown | seconds_to_first_distracted | seconds_to_first_intervention | first_intervention_tier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| read_1 | 30 | 10/30 ≈ 0.333 | 20/30 ≈ 0.667 | 0/30 = 0.0 | 0.027… | 38.852… | 1 |
| phone | 15 | 2/15 ≈ 0.133 | 13/15 ≈ 0.867 | 0/15 = 0.0 | 0.101… | 12.514… | 1 |
| away | 15 | 0/15 = 0.0 | 13/15 ≈ 0.867 | 2/15 ≈ 0.133 | 0.100… | none | none |
| out_of_chair | 15 | 0/15 = 0.0 | 4/15 ≈ 0.267 | 11/15 ≈ 0.733 | 0.100… | none | none |
| read_2 | 30 | 17/30 ≈ 0.567 | 12/30 = 0.4 | 1/30 ≈ 0.033 | 2.176… | 51.277… | 1 |

Compared with the third (face-gate) run: phone/away moved from mostly UNKNOWN to mostly DISTRACTED (`body_no_face` on 13 phone and 10 away rows). Out-of-chair stayed mostly UNKNOWN. Reading improved on read_2 (FOCUSED 13% → 57%); read_1 still has many DISTRACTED, including 11 `body_no_face` when Haar missed the face during reading. An earlier incomplete/invalid S3 attempt (`20261028T045541Z`, session 92, read_1 all UNKNOWN) is not used as a behaviour table.

## Simulated protocol (not measured)

Path B for thesis tables. Generated by `evaluation/thesis_numbers/generate_simulated_selftest.py` — **no webcam, no API, not measured**. Every CSV row has `protocol=SIMULATED` and `measured=false`.

CSV: `evaluation/thesis_numbers/raw/simulated_selftest_protocol.csv` (105 rows)

Rules: reading → FOCUSED; phone/away → DISTRACTED; out_of_chair → UNKNOWN. Same phase keys and 2 s cadence as the live self-test.

| phase | n_heartbeats | focused | distracted | unknown | seconds_to_first_distracted | seconds_to_first_intervention | first_intervention_tier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| read_1 | 30 | 30/30 = 1.0 | 0/30 = 0.0 | 0/30 = 0.0 | none | none | none |
| phone | 15 | 0/15 = 0.0 | 15/15 = 1.0 | 0/15 = 0.0 | 0.0 | none | none |
| away | 15 | 0/15 = 0.0 | 15/15 = 1.0 | 0/15 = 0.0 | 0.0 | none | none |
| out_of_chair | 15 | 0/15 = 0.0 | 0/15 = 0.0 | 15/15 = 1.0 | none | none | none |
| read_2 | 30 | 30/30 = 1.0 | 0/30 = 0.0 | 0/30 = 0.0 | none | none | none |

Do not mix this table with measured live-run tables above.

## Not done / notes

- Live database remains PostgreSQL `FYP_LMS` (not switched to SQLite). Schema for `remediation_events` was created via `db.create_all()` on app start.
- Quiz used for the screenshot has one question; failing it yields error rate 1.0 (> 0.50).
- Module 2 has no alternate document material; the different-format offer was the teacher-saved approved pack on the video content.
- Temporary helper script: `evaluation/thesis_numbers/_tmp_prepare_manual.py` (enrollment/inspection only).
- Fusion checkpoints were not retrained; live S3 used env `ML_FUSION_THRESHOLD=0.75` plus session pose baseline and `body_no_face` (see above).
