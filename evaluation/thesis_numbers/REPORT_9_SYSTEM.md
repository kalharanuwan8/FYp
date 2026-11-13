# REPORT 9 — full-system evidence

**Generated:** 2026-10-29  
**Code under test:** current working tree (not a clean `thesis-final` checkout)  
**Application code edited for this report:** none  
**New tests added:** `evaluation/system_tests/run_report9_system.py` (listed below)

---

## Configuration under test

| Item | Value |
|------|-------|
| `git rev-parse HEAD` | `2974633d05e35e5e54f9cf6654809b5df13d2a9c` (`2974633` — thesis-final-v2 message) |
| Clean `e6c7b17`? | **No.** Working tree is **dirty** (modified and untracked files including DSM-5 work). HEAD is **not** a clean `e6c7b17`. |
| `thesis-final` tag commit | `e6c7b17ec6e448594c4229c751ebc7b781f86ec3` (`git rev-parse thesis-final^{commit}`; corrected 2026-11-04 — was wrongly given as `38be54c…`) |
| `e6c7b17` object | `e6c7b17ec6e448594c4229c751ebc7b781f86ec3` |
| Live API | `http://127.0.0.1:5000` |
| Live fusion threshold | `ML_FUSION_THRESHOLD=0.75` when heartbeat latency servers were started; live `:5000` process used whatever was already configured (harness re-run log shows `fusion_threshold=0.480…` at MLService init) |
| Observed `ml_mode` (live) | **partial** (M1/M2/M4 checkpoints missing; model6 fusion loaded) |
| DB backup before live ST | `evaluation/thesis_numbers/raw/FYP_LMS_backup_before_report9.dump` (107906 bytes) |
| `pytest-cov` | **Not measured** — not importable; not in `backend/requirements.txt`; not installed for this report |

`git status --short` (abridged): modified backend DSM/quiz/analytics paths, frontend DSM/quiz pages, evaluation raw artifacts; untracked `backend/app/services/dsm_indicators.py`, `backend/app/db_models/behaviour.py`, `backend/app/routes/behaviour.py`, `backend/tests/test_dsm_indicators.py`, `evaluation/system_tests/`, REPORT_9 raw logs. Full short status captured at assembly time under the same working tree.

---

## Part 1 — how the system works

### 1.1 Blueprint prefixes

From `backend/app/__init__.py`:

| Prefix | Blueprint |
|--------|-----------|
| `/api/auth` | auth |
| `/api/admin` | admin |
| `/api/courses` | courses + quizzes |
| `/api/session` | session |
| `/api/analytics` | analytics |
| `/api/student` | student_profile |
| `/api/behaviour` | behaviour (DSM idle events) |

### 1.2 Feature inventory (student / teacher / admin)

| Role | Purpose | Frontend | Backend | Primary tables |
|------|---------|----------|---------|----------------|
| All | Login | `frontend/src/pages/.../Login` via `/login` (`App.jsx`) | `POST /api/auth/login` | `users` |
| Admin | Dashboard stats | `/admin/dashboard` | `GET /api/admin/dashboard/stats` | users, students, teachers, sessions |
| Admin | User management / bulk import | `/admin/users` | `/api/admin/users`, `/users/bulk-import`, `/users/<id>/status` | `users`, `students`, `teachers`, consent fields |
| Admin | System settings | `/admin/settings` | `GET/PATCH /api/admin/settings` | `system_settings` |
| Admin | Analytics / logs | `/admin/analytics`, `/admin/logs` | analytics/admin routes | sessions, logs |
| Teacher | Subjects / modules / materials | `/teacher/courses`, `/teacher/courses/:id` | `/api/courses/subjects`, modules, materials | `subjects`, `modules`, `module_contents`, `module_milestone_items` |
| Teacher | Quizzes | CreateQuizModal / QuizEditor | `/api/courses/...` quiz routes | `quizzes`, `quiz_questions`, options |
| Teacher | AI milestone pack draft | Course editor generate-pack UI | `POST /api/courses/materials/generate-pack` | milestones (draft until saved) |
| Teacher | Intervention tier config | subject settings | `GET/PATCH .../intervention-config` | subject intervention settings |
| Teacher | Student list + DSM/analytics | `/teacher/students`, `/teacher/students/:id/analytics` | analytics + DSM profile paths | sessions, quizzes, `behaviour_events`, distraction/intervention logs |
| Student | Browse / enroll | `/student/courses`, SubjectDetail | enrollments + subject detail | `enrollments`, `subjects` |
| Student | Monitored lesson / document | SubjectDetail, DocumentReader | `POST /api/session/start`, heartbeat, stop | `sessions`, `monitoring_observations`, `distraction_events`, `intervention_logs` |
| Student | Quiz attempt | `/student/quizzes/:quizId` | quiz attempt/submit | `quiz_attempts`, `quiz_answers` |
| Student | Analytics | `/student/analytics` | `GET /api/analytics/student` | sessions (observed_v1 fields) |
| Student | Preferences / profile | `/student/settings` (`PreferencesContext.jsx`) | `GET/PATCH /api/student/profile` | `students.ui_preferences`, consent |
| Student | Idle behaviour (record-only) | `useIdleTracker.js`, DocumentReader, QuizAttempt | `POST /api/behaviour/...` | `behaviour_events` |

Routes source: `frontend/src/App.jsx` (role-gated admin/teacher/student trees).

### 1.3 Support-decision trace (live monitoring path)

1. **Heartbeat** — `POST /api/session/<id>/heartbeat` in `backend/app/routes/session.py` accepts optional webcam `image` and noise fields; calls `ml_service.predict_frame_image` when `image` is present; records `MonitoringObservation`; upserts distraction episodes; consults intervention engine and noise monitor.
2. **ML verdict / body rule** — `backend/app/services/ml_service.py` loads available checkpoints; missing M1/M2/M4 → `ml_mode=partial` (observed in live runs). Fusion threshold env can override. Verdicts: `FOCUSED` / `DISTRACTED` / `UNKNOWN` (e.g. no face).
3. **Intervention tiers** — `backend/app/services/intervention_engine.py`: duration bands → tiers 1–4; cooldown; pending lock for tiers that require outcome; ambient tier-1 episode rule; `enabled_tiers` can disable tiers.
4. **Remediation** — `backend/app/services/remediation_service.py`: trigger only when `error_rate >` threshold (default **0.50**); reason from coverage/focus (`decide_reason`); offers guided / pack / alternative content.
5. **Noise** — `backend/app/services/noise_monitor.py`: baseline from first samples; sustained loud streak → one-time environment noise notice without escalating visual tier path when ignored appropriately (covered in unit tests).

### 1.4 Signals recorded but not used as live interventions

From `backend/app/services/dsm_indicators.py` (`INDICATOR_LABELS` and builders): DSM proxies are **profile/analytics only** — they do not drive the live intervention engine.

| Proxy key | Label (implemented) | Sources (implemented) |
|-----------|---------------------|------------------------|
| `dsm1_sustain` | Difficulty sustaining attention (idle) | `behaviour_events` idle ≥ 15 s |
| `dsm2_external` | Easily distracted by external stimuli | camera `distraction_events` + noise notices (count only) |
| `dsm3_finish` | Fails to finish / overtime on quizzes | quiz attempt duration vs quiz time limit |
| `dsm4_careless` | Careless mistakes on easy items | easy-item error streaks |
| `dsm5_hints` | Does not seem to listen (hints on all questions) | `hint_used` on answers |
| `dsm6_effort` | Avoids sustained mental effort (fast + high error) | response_ms + error rate |
| `dsm7_forgetful` | Forgetful in daily activities (missed study goal) | daily goal / progress lookback |

**Explicitly not live interventions:** DSM idle, hint use, response time, overtime, daily-goal miss (recorded / profiled only). Camera DISTRACTED and ambient noise notices remain the live intervention inputs via session heartbeat path.

### 1.5 DSM Table 2.2 mapping (implemented rules only)

Thesis Table 2.2 wording was **not supplied** in-repo for this report → any thesis-specific clinical wording beyond the seven proxy names below is **Not measured**.

| Implemented proxy | Status vs INDICATOR_LABELS | Code |
|-------------------|----------------------------|------|
| DSM-1 idle sustain | **Active** | `dsm_indicators.py` `_idle_count`, `IDLE_MIN_SECONDS = 15` |
| DSM-2 external stimuli | **Active** (camera + noise counts) | `_external_stimuli` |
| DSM-3 finish / overtime | **Active** | `_fails_to_finish` |
| DSM-4 careless easy | **Active** | careless-streak helpers |
| DSM-5 hints-all | **Active** | hint-use aggregation |
| DSM-6 fast+error effort | **Active** | `RANDOM_ERROR_RATE` / `RANDOM_MEDIAN_MS` constants |
| DSM-7 missed daily goal | **Active** | forgetful lookback |

---

## Part 2 — FR01–FR27 / NFR01–NFR12 traceability

**Not measured — requirement tables were not supplied.**

Chapter 6 already names only: `FR-AUTH-03`, `FR-TCH-03`, `FR-ADM-05`, `NFR-PRIV-02`, `NFR-SEC-04` (see `chapter6_evaluation_evidence/CHAPTER6_TEST_CASES.md`). No invented FR01–FR27 / NFR01–NFR12 text.

| ID (chapter6-named only) | Evidence in this report |
|--------------------------|-------------------------|
| `FR-ADM-05` | Live ST-05 admin settings GET → Pass; pytest `test_admin_settings_lifecycle` → Pass |
| `FR-AUTH-03` | pytest `test_register_student_success` → Pass (chapter6 mapping) |
| `FR-TCH-03` | pytest material upload path (`test_security_access` / courses upload family) → Pass in suite |
| `NFR-PRIV-02` | pytest registration pseudonym/consent assertions (chapter6); privacy columns check in Part 6 |
| `NFR-SEC-04` | pytest + live role/unauthenticated cases (Part 5–6) |

---

## Part 3 — unit vs integration (pytest)

### Command (once)

```text
cd backend
..\venvpy312\Scripts\python.exe -m pytest -q -rA
```

### Totals line (exact)

```text
139 passed, 1437 warnings in 32.69s
```

Raw: `evaluation/thesis_numbers/raw/pytest_report9.txt`.

### Coverage

**Not measured** (`pytest-cov` not importable).

### Classification (22 `backend/tests/test_*.py` files)

Rule: **INTEGRATION** if the file uses Flask test client and/or DB via `conftest` / `db.session`; **UNIT** if pure functions / in-memory service / static file checks with no HTTP client and no DB.

| File | Level | n passed | One-line assertion (from `-rA` names) | Result |
|------|-------|----------|----------------------------------------|--------|
| `test_admin.py` | INTEGRATION | 6 | list/deactivate/self-block/bulk-import/settings/non-admin blocked | Pass |
| `test_analytics.py` | INTEGRATION | 1 | analytics endpoints | Pass |
| `test_auth.py` | INTEGRATION | 6 | login validation/invalid/success; register rules; student register | Pass |
| `test_courses.py` | INTEGRATION | 6 | grades, create/own, archive, role list, enroll (+ related) | Pass |
| `test_csv_importer.py` | UNIT | 6 | CSV parse valid + validation errors (+ related) | Pass |
| `test_default_accounts.py` | INTEGRATION | 3 | default demo accounts | Pass |
| `test_dsm_indicators.py` | INTEGRATION | 9 | DSM profile positive/negative + access | Pass |
| `test_face_gate.py` | UNIT | 3 | no-face UNKNOWN does not append buffers (+ related) | Pass |
| `test_gamification.py` | INTEGRATION | 4 | XP/badges paths | Pass |
| `test_intervention_engine.py` | UNIT | 12 | duration bands, tiers, cooldown/pending | Pass |
| `test_intervention_escalation.py` | UNIT | 7 | ambient does not take pending lock; focused reset | Pass |
| `test_milestones_and_triggers.py` | INTEGRATION | 4 | LLM parse mock, generate-pack mock, material milestones, manual trigger | Pass |
| `test_noise_monitor.py` | UNIT | 14 | baseline, streak, pending, lesson-audio ignore, schema | Pass |
| `test_phase1_script_guards.py` | UNIT | 2 | fusion demo script has no filename override; summary F1 bound | Pass |
| `test_phase2a_observation.py` | INTEGRATION | 20 | coverage arithmetic, UNKNOWN, XP claim, landmarker isolation | Pass |
| `test_quizzes.py` | INTEGRATION | 1 | quiz lifecycle + grading | Pass |
| `test_rbac.py` | INTEGRATION | 2 | unauthenticated 401; login token | Pass |
| `test_remediation.py` | INTEGRATION | 10 | error_rate 50% boundary; focus/coverage reasons; API fail→remediation | Pass |
| `test_s3_fusion_runtime.py` | UNIT | 7 | threshold env, body_no_face, baseline, engagement buffer | Pass |
| `test_security_access.py` | INTEGRATION | 4 | uploads blocked; enrolment file; hide answers; quiz read ACL | Pass |
| `test_session.py` | INTEGRATION | 9 | lifecycle, consent, heartbeat, noise, milestone, XP once, stop-active | Pass |
| `test_student_profile.py` | INTEGRATION | 3 | profile lifecycle; student cannot set guardian consent; non-student blocked | Pass |

Suite total **139 passed / 0 failed**.

---

## Part 4 — existing system evaluation harness

### Recorded Run 2 (chapter6)

Source: `chapter6_evaluation_evidence/SYSTEM_EVALUATION_REPORT.md` and `chapter6_evaluation_evidence/evaluation_results_run2.json`.

| Metric | Value |
|--------|-------|
| Pass | **29** |
| Fail | **0** |
| Not executed | **2** (`MON-04` real camera; `ST-06` camera denial UX) |
| `ml_mode_observed` (recorded) | `full` |
| Generated | `20261023T040948Z` |

### Re-run (this report, once)

Command: `dev/test_outputs/system_evaluation/2026-10-23/run_system_evaluation.py`  
Console: `evaluation/thesis_numbers/raw/report9_harness_rerun.txt`  
JSON copy: `evaluation/thesis_numbers/raw/report9_harness_evaluation_results.json` (from `dev/.../logs/evaluation_results.json`, written `2026-10-29`).

```json
{
  "pass": 29,
  "fail": 0,
  "not_executed": 2,
  "total": 31,
  "ml_mode_observed": "partial",
  "generated_at": "20261029T112031Z"
}
```

Harness was **not** edited to force passes. Re-run matches recorded pass/fail/not-executed counts; `ml_mode_observed` differs (`full` historically vs **`partial`** now because checkpoints are missing).

### Catalogue (re-run / Run 2 IDs)

| ID | Components | Expected (short) | Actual (re-run family) | Status |
|----|------------|------------------|------------------------|--------|
| AN-01…AN-05, AN-07 | observation coverage fixtures | independent expected vs `compute_coverage_from_observations` | matched fixture arithmetic | pass |
| AN-06 | student analytics + legacy row | 200; no silent mix | 200 with observed_v1 keys | pass |
| ST-01…ST-05 | student login/enrol/material/quiz/prefs | 200/201 flows | status OK in results JSON | pass |
| ST-06 | camera denial UX | browser deny | not executed | not_executed |
| MON-01 | monitored + blank JPEG | UNKNOWN / no_face | pass (ml_mode partial on re-run) | pass |
| MON-02 | ownership | 403/404 | 404 | pass |
| MON-03 | stop + repeat XP | coverage fields; no double XP | pass | pass |
| MON-04 | real camera | live face verdicts | not executed | not_executed |
| INT-01…INT-05 | pending, milestone, disabled tier, controlled pathway, UNKNOWN | engine contracts | pass | pass |
| TE-01…TE-04 | teacher subject/milestones/generate-pack/config | 200/201 or useful error | pass (TE-03 recorded validation/offline-style outcome historically) | pass |
| AD-01…AD-04 | admin user, consent gate, student consent PATCH, RBAC | create/deactivate; 403s | pass | pass |
| PERF-01 | heartbeat RTT test client | median/p95 recorded | pass | pass |

Full machine rows: `evaluation_results_run2.json` (recorded) and `raw/report9_harness_evaluation_results.json` (re-run).

---

## Part 5 — new live system tests

**Script:** `evaluation/system_tests/run_report9_system.py`  
**Backup first:** `raw/FYP_LMS_backup_before_report9.dump`  
**Evidence dir:** `evaluation/thesis_numbers/raw/report9_system/`  
**Summary:** `summary.json` → **18 pass, 1 fail**  
**Demo accounts:** `admin@luma.com`, `teacher@luma.com`, `student@luma.com`

| ID | FR | Steps | Expected | Actual | Pass/Fail | Evidence |
|----|----|-------|----------|--------|-----------|----------|
| ST-01-admin | no FR text yet | login admin | 200 + token | HTTP 200 | Pass | `st-01-admin.json` |
| ST-01-teacher | no FR text yet | login teacher | 200 + token | HTTP 200 | Pass | `st-01-teacher.json` |
| ST-01-student | no FR text yet | login student | 200 + token | HTTP 200 | Pass | `st-01-student.json` |
| ST-02-student-blocked-teacher | no FR text yet | student GET `/api/analytics/teacher` | 403/401 | HTTP 403 | Pass | `st-02-student-blocked-teacher.json` |
| ST-03-student-blocked-admin | no FR text yet | student GET `/api/admin/users` | 403/401 | HTTP 403 | Pass | `st-03-student-blocked-admin.json` |
| ST-04-admin-stats | no FR text yet | admin dashboard stats | 200 | HTTP 200 | Pass | `st-04-admin-stats.json` |
| ST-05-admin-settings | FR-ADM-05 (chapter6) | admin GET settings | 200 | HTTP 200 | Pass | `st-05-admin-settings.json` |
| ST-06-teacher-subjects | no FR text yet | teacher list subjects | 200 list | HTTP 200 | Pass | `st-06-teacher-subjects.json` |
| ST-07-ai-generate-pack | no FR text yet | teacher generate-pack | 200/201 or documented offline error | **HTTP 200** (milestones returned) | Pass | `st-07-ai-generate-pack.json` |
| ST-08-student-enrollments | no FR text yet | my-enrollments | 200 | HTTP 200 | Pass | `st-08-student-enrollments.json` |
| ST-09-session-start | no FR text yet | monitored start | 201/200 or 403 consent | HTTP 201 | Pass | `st-09-session-start.json` |
| ST-10-heartbeat | no FR text yet | heartbeat 1×1 JPEG | 200 + verdict | HTTP 200; verdict UNKNOWN; `ml_mode=partial` | Pass | `st-10-heartbeat.json` |
| ST-11-trigger-tier1 | no FR text yet | trigger-intervention tier 1 | 200 or 400 | HTTP 200 | Pass | `st-11-trigger-tier1.json` |
| ST-12-session-stop | no FR text yet | stop summary fields | focus/coverage keys | HTTP 200 | Pass | `st-12-session-stop.json` |
| ST-13-repeat-stop-xp | no FR text yet | stop again | 200; no double XP | HTTP 200 | Pass | `st-13-repeat-stop-xp.json` |
| ST-14-preferences | no FR text yet | GET/PATCH/GET theme | theme persists as sage | HTTP 200; `ui_preferences.theme` remained `calm-dark` | **Fail** | `st-14-preferences.json` |
| ST-15-student-analytics | no FR text yet | student analytics | 200 | HTTP 200 | Pass | `st-15-student-analytics.json` |
| ST-16-unauthenticated | no FR text yet | analytics without token | 401 | HTTP 401 | Pass | `st-16-unauthenticated.json` |
| ST-17-perf-login-20 | NFR performance | 20 logins | all 200; median/p95 | HTTP 200; median ≈ 381.5 ms | Pass | `st-17-perf-login-20.json`, `perf_login_20.json` |

### ST-14 failure (not patched)

Harness sent top-level `{"theme":"sage","reduce_motion":true}`. API schema accepts nested `ui_preferences` (`backend/app/routes/student_profile.py`). After PATCH, profile still showed `ui_preferences.theme = "calm-dark"`. Frontend `PreferencesContext.jsx` persists via `{ ui_preferences: next }`. **Fail recorded; application not changed; case not re-run to force a pass.**

### Minimum-list gaps (live ST script)

| Prompt item | Live ST coverage |
|-------------|------------------|
| Role gates / consent / teacher content / AI draft / monitored heartbeat / simulated distraction / stop focus-coverage / XP once / preferences | Covered as above (consent gate observed as 201 with consent already true on demo student; 403 path covered in harness AD-02 / pytest) |
| All tiers off | **Not measured** in live ST script (harness INT-03 covers disabled-tier fallback) |
| Remediation error_rate >50% vs ≤50% | **Not measured** in live ST script (pytest `test_remediation.py` covers boundary and API path) |

Browser screenshots: **not used** (API + JSON evidence sufficient for executed cases).

---

## Part 6 — non-functional

### 6.1 Heartbeat latency (50 timed frames)

Script: `evaluation/thesis_numbers/run_heartbeat_latency.py`  
Raw: `evaluation/thesis_numbers/raw/report9_latency.txt`  
Also wrote `evaluation/thesis_numbers/raw/heartbeat_latency.json`.

| Tag | n | median_ms | p95_linear_ms | ml_modes | n_status_200 |
|-----|---|-----------|---------------|----------|--------------|
| cuda | 50 | **54.083800059743226** | **80.05692010046914** | **partial** | 50 |
| cpu | 50 | **49.03544997796416** | **70.9558098576963** | **partial** | 50 |

Do **not** claim full ML path: both runs report `ml_mode=partial`.

### 6.2 API timings (20 requests)

| Endpoint | n | median_ms | p95_ms | Source |
|----------|---|-----------|--------|--------|
| `POST /api/auth/login` | 20 | 381.5108999842778 | 487.5759999267757 | `raw/report9_system/perf_login_20.json` |
| `POST /api/session/start` (+stop each) | 20 | 29.991299961693585 | 34.41189997829497 | `raw/report9_api_timings.json` |
| `GET /api/analytics/student` | 20 | 31.09170007519424 | 35.74119997210801 | `raw/report9_api_timings.json` |
| Quiz submit ×20 | — | — | — | **Not measured** |

### 6.3 Security (negative cases)

| Case | Source | Result |
|------|--------|--------|
| Unauthenticated `/api/admin/users` → 401 | `test_rbac.py::test_unauthenticated_user_access` | Pass (pytest) |
| Login happy path | `test_rbac.py::test_login` | Pass |
| Public uploads blocked | `test_security_access.py::test_public_uploads_blocked` | Pass |
| Material file requires enrolment/ownership | `test_material_file_requires_enrolment_or_ownership` | Pass |
| Milestone answers hidden from student detail | `test_student_subject_detail_hides_milestone_answers` | Pass |
| Quiz read ACL | `test_quiz_read_requires_ownership_or_enrolment` | Pass |
| Student blocked from teacher analytics | live ST-02 | Pass |
| Student blocked from admin users | live ST-03 | Pass |
| Unauthenticated student analytics | live ST-16 | Pass |

### 6.4 Privacy

- Heartbeat accepts image/audio **in request** for inference (`session.py`); persistence path writes `MonitoringObservation` fields only: `session_id`, `observed_at`, `state`, `confidence`, `face_detected`, `ml_mode`, `reason`, `created_at` (`backend/app/db_models/session.py`).
- Live DB query (`information_schema` via app DB): `monitoring_observations` columns match the model; **no** `bytea` / `image` / `frame` / `audio` / `jpeg` / `blob` columns in public schema name/type match list (empty result). Row count at check: **117**.
- JPEG bytes / mic samples are **not** stored as observation columns.

### 6.5 Degradation

| Check | Evidence | Result |
|-------|----------|--------|
| Face-gate / no-face → UNKNOWN, no buffer append | `test_face_gate.py` | Pass |
| Partial ML load (missing M1/M2/M4) | harness re-run stderr; ST-10; latency warmup | `ml_mode=partial` observed |
| LLM generate-pack | ST-07 | HTTP 200 with milestones (LLM path up for this run) |

### 6.6 Preferences / a11y

Preference keys in `PreferencesContext.jsx` `DEFAULTS`: `theme`, `textSize`, `reduceMotion`, `sounds`, `showCameraPreview`, `breakIntervalMinutes`. Themes: sage, warm, pale-blue, calm-dark.

Live ST-14 attempted top-level theme PATCH → **Fail** (theme not nested under `ui_preferences`). Reloaded profile still had nested `theme: calm-dark`.

Visual / a11y checks: **Not measured**.

---

## Part 7 — models (short; no new training)

Numbers copied from `evaluation/thesis_numbers/REPORT.md` only. Checkpoints for M1/M2/M4/M5 were **not** re-hashed here (weight dirs previously observed missing under `models/outputs/checkpoints/`); no retrain.

| Model | Metric | Value | REPORT.md section |
|-------|--------|-------|-------------------|
| M1 gaze | Test accuracy | 0.6017344896597732 | §1 Test |
| M1 gaze | Test macro-F1 | 0.5593556663019074 | §1 Test |
| M2 pose | Test mean MAE (yaw/pitch/roll mean) | 5.927910881663853 | §2 Test 18–20 |
| M4 engagement | Accuracy | 0.9736842105263158 | §3 |
| M4 engagement | Macro-F1 | 0.9732205778717407 | §3 |
| M5 fusion | Stratified test accuracy / P / R / F1 / ROC-AUC | 1.0 / 1.0 / 1.0 / 1.0 / 1.0 | §4a existing stratified test file |

**How REPORT.md says they were tested:** offline evaluation scripts against held-out / stratified CSVs and checkpoint forward passes (M1 test n=5996; M2 BIWI subjects; M4 25% hold-out on weakly labelled engagement CSV; M5 logistic fusion on `test.csv` and additional blocked splits documented in that file). This REPORT 9 does not re-run those model evaluations.

---

## Part 8 — summary

### Totals by level (from runs above only)

| Level | Pass | Fail | Not executed / Not measured |
|-------|------|------|-----------------------------|
| Unit+Integration pytest | 139 | 0 | coverage Not measured |
| Harness recorded Run 2 | 29 | 0 | 2 (MON-04, ST-06) |
| Harness re-run (Report 9) | 29 | 0 | 2 (MON-04, ST-06) |
| Live system ST (Report 9) | 18 | 1 (ST-14) | remediation live ST + all-tiers-off live ST Not measured |
| FR01–FR27 / NFR01–NFR12 matrix | — | — | **Not measured — tables not supplied** |

### Failures

| ID | Evidence |
|----|----------|
| ST-14-preferences | `evaluation/thesis_numbers/raw/report9_system/st-14-preferences.json` |

### Notable Not measured

| Item | Reason |
|------|--------|
| FR01–FR27 / NFR01–NFR12 full matrix | Tables not pasted |
| Thesis Table 2.2 clinical wording beyond INDICATOR_LABELS | Not supplied |
| pytest-cov line coverage | Package absent |
| Quiz-submit ×20 latency | Not run |
| Visual/a11y preference checks | Not run |
| Live ST “all tiers off” / remediation >50% vs ≤50% | Measured in Part 9 (ST-18, ST-19) |
| Full ML heartbeat path | Checkpoints missing → `ml_mode=partial` (Part 9 search still NOT_FOUND) |

### Traceability matrix

**Not measured — requirement tables were not supplied**, except the five chapter6-named IDs listed in Part 2.

### Raw artifacts index

- `raw/pytest_report9.txt`
- `raw/report9_harness_rerun.txt`
- `raw/report9_harness_evaluation_results.json`
- `raw/FYP_LMS_backup_before_report9.dump`
- `raw/report9_system/` (+ `summary.json`)
- `raw/report9_latency.txt`
- `raw/report9_api_timings.json`
- `raw/heartbeat_latency.json`

---

## Part 9 — fixes

**Date:** 2026-10-29  
**Application code changed:** none (tests/report/docs only for this part’s measurement fixes)  
**New/updated tests:** `evaluation/system_tests/run_report9_system.py` (ST-14 payload), `evaluation/system_tests/run_report9_part9.py`

### 9.1 Checkpoint search (SHA-256)

Searched `*.pt` / `*.pkl` on `D:\`, `C:\Users\Kalhara` (includes Downloads, Desktop, Documents, OneDrive under the profile), `C:\$Recycle.Bin`, `D:\$Recycle.Bin`, `G:\`. Also earlier size-exact scan for baseline byte sizes (27089538 / 134253858 / 2419 / 1853) on `D:\`, `C:\Users\Kalhara`, `G:\` — **no hits**.

Hash log: `evaluation/thesis_numbers/raw/part9_checkpoint_search_pt_pkl.txt`.

| Label (this prompt) | Expected SHA-256 | Baseline path (`dev/BASELINE_CHECKPOINT_HASHES.md`) | Result |
|---------------------|------------------|-----------------------------------------------------|--------|
| M1 | `8127a926…2eba32` | `models/outputs/checkpoints/model1_gaze/best.pt` | **NOT_FOUND** |
| M2 | `a9116270…0f629` | `models/outputs/checkpoints/model2_pose/best.pt` | **NOT_FOUND** |
| M3 | `d39b5f16…beb237e9` | `models/outputs/checkpoints/model4_engagement/model.pkl` | **NOT_FOUND** |
| M4 | `b465e0c48…42020e6` | `models/outputs/checkpoints/model5_fusion/model.pkl` | **NOT_FOUND** |

No files copied into `models/outputs`.

### 9.2 Fusion package currently loaded — and STOP on `ml_mode=full`

**Why model6 loads today** (`backend/app/services/ml_service.py`):

1. `FUSION_CKPT` env unset.
2. `outputs/checkpoints/model6_natural/model.pkl` **exists** → preferred over model5.
3. Observed startup: `Loaded fusion model from model.pkl (kind=model6_mlp)` and `ml_mode=partial` (M1/M2/engagement missing).

**Config-only path to M4 (`b465…` = model5 fusion):** set `FUSION_CKPT` to that file’s absolute path (and `ML_FUSION_THRESHOLD=0.75`). That file is **absent**, so the env cannot point at it.

**`ml_mode=full` also requires** M1 + M2 + engagement (prompt M3) + fusion all loaded. All four hashes **NOT_FOUND**.

**STOP:** restoring `ml_mode=full` with the M4 (`b465…`) package is **impossible without a code change or restoring the missing weight files**. No code change made. No fabricated weights.

### 9.3 Heartbeat latency (full mode)

**Not measured (partial mode)**

### 9.4 ST-14 preferences

| Run | Payload | Result | Evidence |
|-----|---------|--------|----------|
| Original (Report 9 Part 5) | top-level `{"theme":"sage","reduce_motion":true}` | **Fail** — theme stayed `ui_preferences.theme=calm-dark` (test defect vs `PreferencesContext.jsx` / API schema) | `raw/report9_system/st-14-preferences-original-fail.json` (copy of original fail) |
| Part 9 rerun (once) | `{"ui_preferences":{"theme":"sage\|calm-dark","reduceMotion":true}}` | **Pass** — nested prefs persisted | `raw/report9_system/st-14-preferences-rerun.json` |

### 9.5 New live system tests

Script: `evaluation/system_tests/run_report9_part9.py`  
Console: `raw/report9_part9_console.txt`, `raw/report9_part9_console2.txt`  
Summary: `raw/report9_system/summary_part9.json` → final **3 pass / 0 fail**

| ID | Expected | Actual | Pass/Fail | Evidence |
|----|----------|--------|-----------|----------|
| ST-18-empty-tiers-no-intervention | teacher sets all `tier*_enabled=false` → `enabled_tiers=[]`; new session; simulated trigger 1–4 → no visual intervention | HTTP 200 config; triggers returned 409 with `intervention_triggered` false; tiers restored | **Pass** | `st-18-empty-tiers-no-intervention.json` |
| ST-19-remediation-error-rate-boundary | video-module quiz: error_rate >0.50 → remediation offers; ==0.50 → no offer | First attempt **Fail** (single-attempt policy blocked 50% case on same quiz) — preserved `st-19-…-attempt1.json`. Fixed test uses two quizzes; gt50 remediation `error_rate=1.0` with offers; eq50 `correct_count=1`, `remediation=null` | **Pass** (second run) | `st-19-remediation-error-rate-boundary.json` |

### 9.6 pytest

```text
139 passed, 1437 warnings in 45.62s
```

Raw: `evaluation/thesis_numbers/raw/part9_pytest.txt`.

### 9.7 Git commit / tags

| Ref | Value |
|-----|-------|
| Commit message | `thesis submission build` |
| `thesis-submission` / HEAD (authoritative) | `561ee83c618b5024eaad215d7d0bfcaff612280d` (corrected 2026-11-04 — see note) |
| Tag `thesis-final` → commit | `e6c7b17ec6e448594c4229c751ebc7b781f86ec3` |
| Tag `thesis-final-v2` → commit | `2974633d05e35e5e54f9cf6654809b5df13d2a9c` |
| Tag `thesis-run5-evaluated` → commit | `a3a3c7ba9e54f92e329c7f6b2e581823111d1c3c` (a branch of the same name points to the same commit, so git's "ambiguous refname" warning is harmless) |

Excluded from commit: `*.dump` DB backups, `heartbeat_*.db`, and other unstaged REPORT7 raw logs.

**Correction (2026-11-04).** The cell originally read `ef043094…`, the hash of the commit *before* this report was amended into it. A commit cannot record its own hash, so that value was necessarily stale. `git rev-parse thesis-submission^{commit}` = `561ee83c618b5024eaad215d7d0bfcaff612280d`, which is the authoritative value.

### 9.8 DSM indicators (record-only)

**Do not trigger live interventions.** Idle posts go to `/api/behaviour/idle`; profile is read-only analytics. Camera DISTRACTED / noise notices remain the live intervention inputs; DSM only **counts** some of those under DSM-2 for the teacher profile.

Teacher UI: `/teacher/students` → “DSM-5 indicators” → `/teacher/students/:studentId/analytics` (`frontend/src/pages/teacher/StudentAnalytics.jsx`).  
API: `GET /api/analytics/teacher/students/<id>/dsm-profile`.

| ID | Label | Exact constants / rule (`dsm_indicators.py`) |
|----|-------|-----------------------------------------------|
| `dsm1_sustain` | Difficulty sustaining attention (idle) | `IDLE_MIN_SECONDS = 15.0` — count idle `behaviour_events` with duration ≥ 15 s |
| `dsm2_external` | Easily distracted by external stimuli | Count camera `distraction_events` with verdict distracted + `environment_noise_notice` logs in window (no extra numeric threshold beyond existing systems) |
| `dsm3_finish` | Fails to finish / overtime on quizzes | Attempt elapsed minutes > `quiz.time_limit_minutes` (incomplete or completed overtime) |
| `dsm4_careless` | Careless mistakes on easy items | `CARELESS_EASY_STREAK = 3` consecutive wrong answers on `difficulty=="easy"` |
| `dsm5_hints` | Does not seem to listen (hints on all questions) | `HINT_ALL_MIN_QUESTIONS = 3`; every question in attempt has `hint_used` |
| `dsm6_effort` | Avoids sustained mental effort (fast + high error) | `RANDOM_ERROR_RATE = 0.70` and `RANDOM_MEDIAN_MS = 5000` — error_rate ≥ 0.70 and median `response_ms` < 5000 |
| `dsm7_forgetful` | Forgetful in daily activities (missed study goal) | `FORGETFUL_LOOKBACK_DAYS = 7` (excludes today); day study minutes < `StudentProgress.daily_goal_minutes` (default 20 if no progress row) |

Profile also returns these under `constants` in the API payload.
