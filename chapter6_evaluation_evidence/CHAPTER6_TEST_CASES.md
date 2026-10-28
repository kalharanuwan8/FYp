# Chapter 6 test-case catalogue — Luma

**Catalogue prepared:** 2026-10-24  
**Recorded execution window:** 2026-10-23  
**Build recorded with the evaluation:** branch `camtesting`, HEAD `b6ea923ff1819ef12212456ad5295726f3147b24`, Phase 2A accounting `6b1d6541fc551a367038b569f18db1904c7df481`. Uncommitted theme UI was present, so that commit alone does not reproduce the evaluated interface.  
**Platform:** Windows 11 Pro 10.0.26200, Python 3.12.5, Torch 2.5.1+cu121.

This catalogue exports tests that already exist. It does not re-run them, change application behaviour, or replace the historical result files. Proposed checks are listed only in [CHAPTER6_TEST_GAPS.md](CHAPTER6_TEST_GAPS.md) and are not given a Pass status.

Field-split rows for every case are in [CHAPTER6_TEST_CASES.csv](CHAPTER6_TEST_CASES.csv) (137 rows: 131 Pass, 6 Not executed). Source paths are in [CHAPTER6_TEST_SOURCES.md](CHAPTER6_TEST_SOURCES.md).

## 1. Evidence used

| Source | What it records |
|--------|-----------------|
| `evaluation_results_run1.json` | Harness Run 1, 2026-10-23T04:07:36Z. 27 pass, 2 fail, 2 not executed. |
| `evaluation_results_run2.json` | Harness Run 2, 2026-10-23T04:09:48Z. 29 pass, 0 fail, 2 not executed. |
| `run_system_evaluation.py` | Procedures and the pass predicates actually coded. |
| `api_samples/*.json` | Saved bodies. Several IDs are cited by the harness and stored only inside the results JSON; those sample files were not copied into this folder. |
| `backend_pytest.txt` | Quiet pytest: **94 passed**, 0 failed, 35.10 s. Node ids are not printed. |
| `dev/test_outputs/system_evaluation/2026-10-23/heartbeat_rtt.csv` | PERF-01 samples (Run 2 figures). |
| `dev/test_outputs/system_evaluation/2026-10-23/intervention_display_timing.csv` | BR-02 / BR-03 timers. |
| `dev/test_outputs/phase2a_correction_browser_check.txt` | Mock-camera browser notes, 2026-10-23. |
| `dev/UI_THEME_IMPLEMENTATION.md` and `dev/test_outputs/ui_theme_screenshots/` | Settings and chrome screenshots. |
| `backend/tests/test_*.py` | Assertions behind the 94 passes, plus three later untracked tests. |

The quiet pytest log matches the **94** `test_*` functions in the committed modules. `backend/tests/test_default_accounts.py` (3 functions) is untracked and is outside that count, so those three are **Not executed** in this pack.

`logs/not_executed.txt` says MON-04 and ST-06 were executed in the browser section. The harness JSON, the evaluation report, and the browser note disagree: the browser used a canvas `captureStream` mock, and both IDs remain `not_executed`. This catalogue follows the harness status.

Harness, browser, and pytest rows overlap. Their pass counts must not be added together.

## 2. How to read a row

| Field | Rule used here |
|-------|----------------|
| Status | **Pass**, **Fail**, **Blocked**, or **Not executed**. Latest recorded execution. Run 1 failures stay in the actual-result text. |
| Requirement ID | Filled only where the executed code is already labelled in the repository: `FR-AUTH-03` and `NFR-PRIV-02` on the user row asserted by registration; `FR-TCH-03` on file uploads; `FR-ADM-05` on admin settings. `FR-AUTH-06` is a comment on the unregistered `sessions.py` blueprint, so the recorded consent tests are not given that ID. Other rows use the harness wording or “no formal ID”. |
| Test level | unit, integration, browser, or performance. |
| Input origin | **mocked** (patched collaborator or fake media device), **injected** (verdict, episode, or rows written into the decision path), **real device** (none of the executed rows), or **fixture** (constructed accounts and payloads). |
| Evidence narrower than the title | Yes when the assertions or saved body support a smaller claim than the test name or harness requirement line. |

Pytest actual result, unless a row says otherwise: included in the 2026-10-23 run of 94 passed. The log does not name the function; the function is one of the 94 committed tests.

## 3. Representative cases for the chapter body

Use this table in Chapter 6. The appendix and the CSV are the full list. Where the evidence is narrower than the title, the “Recorded result” column states the smaller claim.

| ID | Requirement | Level | Recorded result that may be cited | Status | Evidence |
|----|-------------|-------|-----------------------------------|--------|----------|
| ST-01 | Student login | integration | `POST /api/auth/login` returned 200 with an access token (Run 1 and Run 2). | Pass | `api_samples/st01_login.json` |
| ST-02 | Enrolment access | integration | `GET /api/courses/my-enrollments` returned 200 with one enrolment (Run 1 and Run 2). | Pass | `api_samples/st02_enrollments.json` |
| ST-04 | Quiz submit accepted | integration | Attempt created (201, `attempt_id=1`) and submit returned 200. The saved body has no score and no per-answer correctness. Correctness is the separate pytest `test_quiz_full_lifecycle_and_grading`. | Pass | `api_samples/st04_quiz.json` |
| ST-05 | Theme value stored on the profile | integration | PATCH/GET stored `theme=sage` and `daily_goal_minutes=25`. This is profile JSON. It does not show `data-theme` or colours on screen. | Pass | Run 2 result object. Cited `api_samples/st05_prefs.json` is not in this folder. |
| ST-06 | Camera denial | browser | No denial run was recorded. | **Not executed** | Harness result; `dev/.../logs/not_executed.txt` |
| MON-01 | Blank frame → UNKNOWN | integration | Monitored start 201; blank JPEG heartbeat 200; `verdict=UNKNOWN`, `reason=no_face`, `confidence=null`, `face_detected=false`, `ml_mode=full`. Checkpoints were loaded. The no-face path does not show a usable fusion label. | Pass | `api_samples/mon01_heartbeat.json` |
| MON-03 | Stop returns `observed_v1` | integration | Two stops both returned 200 with `xp_gained=0`, null focus, and 0% coverage. Repeating a zero award does not show that a positive award is issued once. | Pass | `api_samples/mon03_stop.json` |
| MON-04 | Physical camera | integration | No physical webcam run was recorded. | **Not executed** | Harness result |
| INT-01 | Pending lock on a manual trigger | integration | Manual tier 1 returned `ambient_cue` (200); an immediate tier 2 returned 409; after a response, tier 2 returned `pacing_pause`. The manual route skips duration and cooldown. | Pass | `api_samples/int01_manual_pending.json` |
| INT-02 | Milestone response stored | integration | Manual tier 3 returned `milestone_quiz`; the response was stored with `user_response=reengaged` and `is_correct=null`. Grading is not shown. | Pass | Run 2 result. Sample file not in this folder. |
| INT-03 | One disabled tier, manual trigger, new session | integration | Tier 2 disabled, new session, manual tier 2 returned `ambient_cue`. All four tiers off, and the automatic cooldown, are different tests. | Pass | Run 2 result. Sample file not in this folder. |
| INT-04 | Duration band with cooldown 0 | integration | Injected `DISTRACTED` and an aged episode returned `intervention_triggered=true`, `intervention_type=ambient_cue`. Fixture cooldown was 0. | Pass | `api_samples/int04_controlled_pathway.json` |
| INT-05 | UNKNOWN heartbeat does not fire | integration | Heartbeat 200, `verdict=UNKNOWN`, `intervention_triggered=false`. | Pass | Run 2 result. Sample file not in this folder. |
| TE-02 | Read and save milestones | integration | Run 1: GET returned 500 (Fail). Run 2, after a harness URL correction and no product change: GET 200 with 1 milestone, PATCH 200. | Pass | `api_samples/te02_milestones.json` (Run 2 body) |
| TE-03 | Missing `description` is rejected | integration | `POST /materials/generate-pack` without `description` returned 400 `Validation failed` (`description` required). No pack was generated and Ollama was not called. | Pass | `api_samples/te03_generate_pack.json` |
| AN-01 | `observed_v1` mixed interval | unit | Hand-calculated F=8, D=2, U=10, focus 80%, coverage 50% matched `compute_coverage_from_observations`. | Pass | `analytics_fixtures.json`; Run 2 result |
| AN-06 | Legacy 88% is absent from the `observed_v1` average | integration | Student analytics 200; `avg_focus_percentage=0.0`, `avg_monitoring_coverage_pct=18.3` (Run 2), `focus_metric_version=observed_v1`. The average is not ~88. | Pass | `api_samples/an06_analytics.json` |
| AN-07 | Zero observed focus awards 0 XP | unit | `award_session_xp(observed_focused_seconds=0)` returned `xp_gained=0`. | Pass | Run 2 result |
| PERF-01 | Blank-JPEG heartbeat handling time | performance | Flask test client, 35 steady samples after one colder request: median 34.38 ms, p95 42.08 ms, 0 failures (Run 2). Run 1 steady median was 37.85 ms. This is server handling of a no-face frame, not browser round-trip and not detection latency. | Pass | `dev/.../heartbeat_rtt.csv` |
| BR-02 | Ambient cue leaves playback running | browser | DemoPanel tier 1: overlay text seen, playback continued. One click-to-DOM time was 996.3 ms. | Pass | `intervention_display_timing.csv`; mock camera |
| BR-03 | Pacing pauses playback | browser | After ambient was dismissed, DemoPanel tier 2 left `video.paused=true`. Overlay-text poll did not complete. | Pass | `intervention_display_timing.csv`; mock camera |
| `test_repeated_stop_awards_xp_only_once` | Positive session XP once | integration | First stop `xp_gained > 0` from injected FOCUSED observations; second stop `xp_gained == 0` and stored XP unchanged. | Pass | `backend/tests/test_session.py`; pytest log |
| `test_cooldown_suppresses_repeat` | Cooldown window | unit | Engine constructed with 60 s cooldown: fire at t=100; pending blocks; after `reengaged`, still `None` at t=130; fires again at t=165. | Pass | `backend/tests/test_intervention_engine.py` |
| `test_all_tiers_disabled_fires_nothing` | Empty tier set | unit | `enabled_tiers=[]` stays empty and `decide_intervention` returns `None` for a 50 s episode. | Pass | `backend/tests/test_intervention_engine.py` |
| `test_quiz_full_lifecycle_and_grading` | Quiz scoring | integration | Correct MCQ plus trimmed case-insensitive short answer scored 100 with both `is_correct` true. Duplicate question ids, resubmit, and a second attempt were rejected. | Pass | `backend/tests/test_quizzes.py` |
| `test_generate_pack_endpoint_mocked` | Generate-pack success contract | integration | With `generate_material_pack` patched, the route returned 200, the fake summary, and one milestone. Ollama was not contacted. | Pass | `backend/tests/test_milestones_and_triggers.py` |

## 4. Cases where the evidence is narrower than the title

These rows stay **Pass** for the smaller claim. They are not evidence for the wider reading.

| ID or function | Wider reading | What the assertions or body show |
|----------------|---------------|-----------------------------------|
| TE-03 | Successful generation, or a handled Ollama outage | HTTP 400 because `description` was absent. The harness treats any of 200, 201, 400, 404, 500, 502, 503 as pass, so this predicate does not distinguish validation from an outage. The route maps `LLMUnavailableError` to 503; that branch was not executed. |
| MON-03 | Positive-XP idempotency | Both responses have `xp_gained=0`. |
| INT-01, and the manual half of INT-03 | Automatic cooldown or duration rules | `POST …/trigger-intervention` is defined to skip those gates. INT-01 shows the pending lock (409) and tier types. |
| INT-02 | Milestone answer graded | Saved `is_correct` is null. `test_manual_trigger_and_milestone_grading` is the grading evidence (`is_correct is True`). |
| INT-04 | Production cooldown (engine default 30 s) | Fixture set `intervention_min_cooldown_seconds` to 0, then an injected DISTRACTED episode fired `ambient_cue`. |
| INT-03 | Every tier disabled | Only tier 2 was turned off. Fallback was `ambient_cue` on a manual trigger. |
| ST-04 | Quiz correctness | Status codes and `attempt_id` only. |
| ST-05 and `test_ui_preferences_patch` | Theme is applied visually | Profile JSON (`sage` in the harness; `calm-dark` on the PATCH response in pytest). No computed style and no screenshot in those tests. |
| TE-01 | Create and edit of learning content | Run 2 records subject creation 201 and the response keys. No content edit is in the actual object. |
| TE-04 | Tier configuration saved | Actual object is `get_or_patch: 200` only. |
| ST-03 | Material opened | Actual object is HTTP 200. The sample file contains the module payload; the harness pass predicate checks the status code. |
| PERF-01 | End-to-end or model latency | Test-client time for a blank JPEG that resolves to UNKNOWN / `no_face`. The CSV header mentions `ml_infer`; on this path a fusion label is not produced. |
| `test_award_session_xp_and_first_badge` | `observed_v1` focus XP | Calls `award_session_xp` with `focus_percentage=80` and no `observed_focused_seconds`, which is the legacy duration × focus branch (8 minutes, 16 XP, `first_session` badge). |
| `test_heartbeat_with_image_returns_ml_verdict` | A FOCUSED or DISTRACTED classification | Blank frame, and a client-supplied `verdict=FOCUSED`, still returns UNKNOWN / `no_face` and `intervention_triggered=false`. |
| `test_llm_service_parses_json_pack` and `test_generate_pack_endpoint_mocked` | Live Ollama | `_chat` or `generate_material_pack` is patched. |
| BR-02 timing | A latency estimate | One DemoPanel observation, 996.3 ms, mock camera. |
| AN-01 versus `test_coverage_valid_observations_and_gaps` | Same numeric proof | The pytest asserts a positive mix that sums to 20 s. The exact 8 / 2 / 10 / 80% / 50% figures are the harness comparison, not that pytest. |

Run 1 TE-02 (HTTP 500) and AD-01 (create HTTP 400, deactivate not called) are historical **Fail** rows. The evaluation report attributes them to the harness (wrong URL; missing guardian fields and a duplicate email). Run 2 recorded Pass after harness-only changes. The product status in this catalogue is the Run 2 Pass, with the Run 1 body retained below.

## 5. Appendix A — harness catalogue (IDs preserved)

Common preconditions: Flask app in testing mode, isolated `*@luma.demo` accounts, course “Eval System Course”, `observed_v1`, and `intervention_min_cooldown_seconds=0` in the fixture. Execution date 2026-10-23. Build as in the header. No real camera or microphone.

### AN-01 — observed_v1 mixed coverage

- **Requirement ID:** none in the repository. Requirement text: `observed_v1` mixed coverage.
- **Level:** unit. **Origin:** injected observation timestamps.
- **Input:** FOCUSED at 0 s and 2 s, DISTRACTED at 10 s, FOCUSED at 12 s, session length 20 s.
- **Steps:** Compare a hand calculation with `compute_coverage_from_observations`.
- **Expected:** focused 8, distracted 2, unknown 10, focus 80%, coverage 50%.
- **Actual:** those values, `focus_metric_version=observed_v1`. Run 1 and Run 2 pass.
- **Status:** Pass. **Evidence:** `analytics_fixtures.json`, both results files. **Function:** harness `AN-01`.

### AN-02 — gap after T_support

- **Level:** unit. **Origin:** injected.
- **Input:** DISTRACTED at 0 s and 4 s, session 10 s. `T_support=3`.
- **Expected:** focused 0, distracted 6, unknown 4, focus 0%, coverage 60%.
- **Actual:** match. **Status:** Pass (both runs).

### AN-03 — UNKNOWN-only session

- **Level:** unit. **Origin:** injected.
- **Input:** UNKNOWN observations only, session 30 s.
- **Expected:** focus null, coverage 0, unknown 30.
- **Actual:** match, including `focus_percentage=null`. **Status:** Pass (both runs).

### AN-04 — clip at session end

- **Level:** unit. **Origin:** injected.
- **Input:** FOCUSED at 0 s, session end at 2 s.
- **Expected:** focused 2, unknown 0.
- **Actual:** focused 2, unknown 0, focus 100%, coverage 100%. **Status:** Pass (both runs).

### AN-05 — empty session

- **Level:** unit. **Origin:** fixture with no observations.
- **Input:** no observations, session 60 s.
- **Expected:** focus null, unknown 60.
- **Actual:** match, coverage 0. **Status:** Pass (both runs).

### ST-01 — student login

- **Level:** integration. **Origin:** fixture account.
- **Steps:** `POST /api/auth/login`.
- **Expected:** 200 and an access token.
- **Actual:** 200, `has_token=true`. **Status:** Pass (both runs). **Evidence:** `api_samples/st01_login.json`.

### ST-02 — enrolment list

- **Level:** integration. **Origin:** fixture enrolment.
- **Steps:** `GET /api/courses/my-enrollments`.
- **Expected:** 200 and the eval course.
- **Actual:** 200, count 1. **Status:** Pass (both runs). **Evidence:** `api_samples/st02_enrollments.json`.

### ST-03 — material metadata

- **Level:** integration. **Origin:** fixture module.
- **Steps:** GET subject/module.
- **Expected in the harness:** HTTP 200.
- **Actual:** 200. **Status:** Pass (both runs). **Evidence:** `api_samples/st03_material.json`.
- **Narrower than a “content opened” claim:** the pass predicate is the status code. The sample file holds the module JSON.

### ST-04 — quiz attempt and submit

- **Level:** integration. **Origin:** fixture quiz `2+2=?` with a correct option.
- **Steps:** POST attempt, then POST submit.
- **Expected in the harness:** attempt created and submit 200.
- **Actual:** attempt 201 (`attempt_id=1`), submit 200. Sample keys are `attempt`, `attempt_status`, `submit_status` only.
- **Status:** Pass (both runs). **Evidence:** `api_samples/st04_quiz.json`.
- **Does not establish:** score or `is_correct`.

### ST-05 — preference JSON

- **Level:** integration. **Origin:** fixture profile.
- **Steps:** PATCH then GET `/api/student/profile`.
- **Expected:** theme `sage` persisted.
- **Actual:** patch 200; preferences `daily_goal_minutes=25`, `theme=sage`.
- **Status:** Pass (both runs). **Evidence:** Run 2 `evaluation_results_run2.json` (cited sample file absent here).
- **Does not establish:** visual application. See UI-THEME rows.

### ST-06 — camera denial

- **Level:** browser. **Origin:** would require a real permission denial.
- **Expected:** monitored session does not start, or an error is shown.
- **Actual:** harness text “Deferred to browser suite”. Browser note: permission was unavailable and a canvas mock was used.
- **Status:** **Not executed**. **Evidence:** both results files.

### MON-01 — blank JPEG heartbeat

- **Level:** integration. **Origin:** synthetic image (blank JPEG), not a device.
- **Steps:** start monitored session; POST heartbeat with a blank JPEG.
- **Expected:** UNKNOWN, `no_face`, null confidence, `face_detected=false`.
- **Actual:** start 201, heartbeat 200, those fields, `ml_mode=full`. **Status:** Pass (both runs). **Evidence:** `api_samples/mon01_heartbeat.json`.

### MON-02 — session ownership

- **Level:** integration. **Origin:** fixture second student.
- **Steps:** another student posts a heartbeat into the session.
- **Expected:** 403 or 404.
- **Actual:** 404. **Status:** Pass (both runs). **Evidence:** Run 2 result (cited `api_samples/mon02_ownership.json` absent here).

### MON-03 — stop, then stop again

- **Level:** integration. **Origin:** fixture session with no focused observations.
- **Steps:** `POST …/stop` twice.
- **Expected line:** first 200 with coverage fields; second adds no XP.
- **Actual:** stop 1: 200, focus null, coverage 0, xp 0, metric `observed_v1`. Stop 2: 200, xp 0. Saved body also has `unknown_seconds=20.784` and progress XP 35 unchanged by this stop.
- **Status:** Pass (both runs). **Evidence:** `api_samples/mon03_stop.json`.
- **Does not establish:** a positive award issued once. That is `test_repeated_stop_awards_xp_only_once`.

### MON-04 — physical camera

- **Level:** integration. **Origin:** real device, not used.
- **Expected line:** live FOCUSED or DISTRACTED with a face.
- **Actual:** “Not executed in this harness”.
- **Status:** **Not executed**.

### INT-01 — manual pending lock

- **Level:** integration. **Origin:** injected manual tier, not an episode timer.
- **Steps:** manual tier 1; immediate tier 2; respond; tier 2 again.
- **Expected:** pending blocks the overlap; after the response, tier 2 fires.
- **Actual:** tier 1 200 `ambient_cue`; next 409; tier 2 200 `pacing_pause`. Note in the result: manual trigger bypasses duration and cooldown.
- **Status:** Pass (both runs). **Evidence:** `api_samples/int01_manual_pending.json`.

### INT-02 — milestone response

- **Level:** integration. **Origin:** manual tier 3.
- **Steps:** trigger tier 3; post a response with `selected_option`.
- **Expected line:** 200 and response recorded.
- **Actual:** tier 3 200 `milestone_quiz`; grade status 200; `is_correct=null`; `user_response=reengaged`; message “Intervention response recorded successfully”.
- **Status:** Pass (both runs). **Evidence:** Run 2 result (sample file absent here).
- **Does not establish:** a correct or incorrect grade.

### INT-03 — tier 2 disabled

- **Level:** integration. **Origin:** config change plus manual trigger.
- **Steps:** disable tier 2, start a new session, trigger tier 2.
- **Expected:** fallback `ambient_cue`, not `pacing_pause`.
- **Actual:** 200, type `ambient_cue`. Result note: config is loaded when the session engine is built.
- **Status:** Pass (both runs). **Evidence:** Run 2 result (sample file absent here).
- **Does not establish:** all tiers disabled, or cooldown.

### INT-04 — injected distracted episode

- **Level:** integration. **Origin:** injected TESTING verdict; episode backdated; cooldown fixture 0.
- **Steps:** controlled DISTRACTED heartbeat after the episode is older than 5 s.
- **Expected:** `ambient_cue` may fire for the 5–10 s band.
- **Actual:** 200, `triggered=true`, type `ambient_cue`, `reason=test_injected`, `verdict=DISTRACTED`.
- **Status:** Pass (both runs). **Evidence:** `api_samples/int04_controlled_pathway.json`.
- **Does not establish:** the 30 s default cooldown. See `test_cooldown_suppresses_repeat`.

### INT-05 — UNKNOWN does not fire

- **Level:** integration. **Origin:** injected UNKNOWN heartbeat after distraction.
- **Expected:** verdict UNKNOWN and `intervention_triggered=false`.
- **Actual:** 200, those two fields.
- **Status:** Pass (both runs). **Evidence:** Run 2 result (sample file absent here).
- **Does not establish:** that the open episode row was closed. That is `test_unknown_closes_open_distraction_episode`.

### TE-01 — create subject

- **Level:** integration. **Origin:** fixture teacher.
- **Steps:** `POST` subject.
- **Expected line:** 200/201 or recoverable.
- **Actual Run 2:** 201; body keys include `id`, `title`, `grade_level_id`, `is_archived`, timestamps.
- **Status:** Pass (both runs). **Evidence:** Run 2 result (cited sample absent here).
- **Does not establish:** an edit of an existing lesson.

### TE-02 — milestones

- **Level:** integration. **Origin:** fixture milestone on “Eval Demo Video”.
- **Steps:** `GET` and `PATCH /api/courses/materials/<id>`.
- **Expected:** 200 with milestones.
- **Actual Run 1:** GET 500. **Fail.**
- **Actual Run 2:** GET 200, `milestone_count=1`, PATCH 200. Question text “What is the main idea of this demo lesson?”, `correct_option=0`.
- **Status:** Pass on Run 2. **Evidence:** `api_samples/te02_milestones.json`.

### TE-03 — generate-pack request without a description

- **Requirement text in the harness:** “Generate material pack / Ollama availability”.
- **Level:** integration. **Origin:** fixture teacher; body was `content_id`, then `module_content_id`. No `description`.
- **Steps:** `POST /api/courses/materials/generate-pack`. On a status ≥ 400 the harness retries with `module_content_id` and records the second response.
- **Expected line:** 200 if Ollama is up; a useful error if it is down.
- **Actual:** 400, error “Validation failed”, details field `description` / “Field required”.
- **Status:** Pass under the harness predicate (both runs). **Evidence:** `api_samples/te03_generate_pack.json`.
- **Supported claim:** a pack request without `description` is rejected before generation.
- **Unsupported:** a successful pack, an Ollama HTTP error, or HTTP 503 `LLMUnavailableError`.

### TE-04 — intervention config HTTP status

- **Level:** integration. **Origin:** fixture subject.
- **Steps:** GET config; if that fails, PATCH; otherwise PATCH as well. The recorded status is the GET status when GET succeeded.
- **Expected:** 200.
- **Actual:** `get_or_patch=200`.
- **Status:** Pass (both runs). **Evidence:** Run 2 result (sample file absent here).
- **Does not establish:** the saved enabled-tier set.

### AD-01 — admin create and deactivate

- **Level:** integration. **Origin:** fixture admin. No formal requirement ID on this route; `FR-AUTH-03` is the `created_by` column, which this harness row does not assert.
- **Steps:** register, then PATCH status.
- **Expected:** create 201/200 and deactivate 200.
- **Actual Run 1:** create 400, deactivate null. **Fail.**
- **Actual Run 2:** create 201, deactivate 200.
- **Status:** Pass on Run 2. **Evidence:** Run 2 result (sample file absent here).

### AD-02 — consent gate

- **Requirement ID:** none on the registered route. The 403 string comes from `backend/app/routes/session.py`. A similar comment, `FR-AUTH-06`, is on the unregistered `sessions.py` blueprint and is not applied to this result.
- **Level:** integration. **Origin:** fixture student without consent.
- **Steps:** start a monitored session.
- **Expected:** 403.
- **Actual:** 403, error “Parental/Guardian consent required for monitored learning sessions”.
- **Status:** Pass (both runs). **Evidence:** Run 2 result (sample file absent here).

### AD-03 — student cannot change guardian consent

- **Level:** integration. **Origin:** fixture student.
- **Steps:** student PATCH consent.
- **Expected:** 403 or 401.
- **Actual:** 403.
- **Status:** Pass (both runs). **Evidence:** Run 2 result (sample file absent here).

### AD-04 — wrong role

- **Level:** integration. **Origin:** fixture student token.
- **Steps:** `GET /api/admin/users`.
- **Expected:** 403.
- **Actual:** 403.
- **Status:** Pass (both runs). **Evidence:** Run 2 result (sample file absent here).

### AN-06 — legacy row and student analytics

- **Level:** integration. **Origin:** fixture legacy session (`focus_percentage=88`, `focus_metric_version` empty) plus observed sessions.
- **Steps:** `GET /api/analytics/student`.
- **Expected line:** 200 and a labelled separation so the average is not dominated by 88.
- **Actual Run 2:** 200, `avg_focus_percentage=0.0`, `avg_monitoring_coverage_pct=18.3`, version `observed_v1`. Run 1 coverage was 19.7 with the same 0.0 focus.
- **Status:** Pass (both runs). **Evidence:** `api_samples/an06_analytics.json`.
- **Supported claim:** the returned average is 0.0, not ~88, and the payload is labelled `observed_v1`.

### AN-07 — zero focused seconds

- **Level:** unit. **Origin:** direct service call.
- **Steps:** `award_session_xp(observed_focused_seconds=0)`.
- **Expected:** `xp_gained=0`.
- **Actual:** 0, `focus_minutes=0`, no new badges. Progress XP stayed 35.
- **Status:** Pass (both runs).

### PERF-01 — heartbeat handling time

- **Level:** performance. **Origin:** synthetic blank JPEG.
- **Steps:** 1 cold heartbeat, then 35 steady heartbeats, Flask test client.
- **Expected:** at least 30 samples; report median and p95.
- **Actual Run 2:** n=35, failures=0, cold 163.98 ms, median 34.38 ms, p95 42.08 ms. Run 1: cold 170.15 ms, median 37.85 ms, p95 50.45 ms.
- **Status:** Pass (both runs). **Evidence:** `dev/test_outputs/system_evaluation/2026-10-23/heartbeat_rtt.csv` (Run 2 samples). The copy named in the thesis-folder README is not in this folder.
- **Supported claim:** server-side handling time of the no-face heartbeat on that client.

## 6. Appendix B — browser and theme records

Camera input for BR-01–BR-04 and the Phase 2A browser note was a **mocked** `getUserMedia` / canvas `captureStream`. Demo login and the local file `/uploads/phase2a_demo.mp4` were fixtures. Date 2026-10-23. Same build as the header.

| ID | Title | Level | Preconditions and steps | Expected | Actual | Status | Evidence |
|----|-------|-------|-------------------------|----------|--------|--------|----------|
| BR-01 | Student dashboard | browser | Log in as the Phase 2A demo student and open the dashboard. | Dashboard loads. | Loaded. | Pass | `screenshots/01_student_dashboard.png` |
| BR-02 | Ambient leaves playback running | browser | Open the demo video with the mock camera. DemoPanel tier 1. | Playback continues; overlay can appear. | `playing` continued; overlay ~996.3 ms after one click. | Pass | `screenshots/02_video_player.png`; `intervention_display_timing.csv`; Phase 2A browser note item 1 (`pauseCalls=0`, t≈4.4 s) |
| BR-03 | Pacing pauses playback | browser | Dismiss ambient, then DemoPanel tier 2. | Video pauses. | `video.paused=true`, `pauseCalls≥1`. Overlay-text poll incomplete. | Pass | `intervention_display_timing.csv`; Phase 2A browser note item 2 |
| BR-04 | Analytics shows focus and coverage | browser | Open the progress / analytics page. | Both figures visible. | 0% average focus and 3% monitoring coverage. | Pass | `screenshots/03_student_analytics.png` |
| P2A-BR-3 | UNKNOWN shown for synthetic frames | browser | Demo panel with blank synthetic frames. Not a harness ID. | UNKNOWN displayed. | Verdict UNKNOWN, confidence “—”, model full. | Pass | `dev/test_outputs/phase2a_correction_browser_check.txt` item 3 |
| P2A-BR-4 | Stop releases the mock capture | browser | Complete the session. | No live `MediaStream` tracks left on video elements. | Player closed; no live tracks on video elements. This is the mock stream. | Pass | same file, item 4 |
| UI-THEME-SETTINGS | Settings chrome for four themes | browser | Demo student `student@luma.com`. Switch Sage, Warm, Pale blue, Calm dark. | Saved confirmation and a visible theme change. | Warm screenshot shows a parchment page and “Saved”. Calm-dark screenshot shows a dark page, dark cards, and “Saved”. Sage login, dashboard, settings, and courses screenshots were archived. | Pass for settings and listed chrome only | `dev/UI_THEME_IMPLEMENTATION.md` §6; `dev/test_outputs/ui_theme_screenshots/01`–`07` |
| UI-THEME-LEARNING | Theme on lesson, quiz, and intervention screens | browser | Would need an enrolled subject with a quiz. | Tokens applied on those screens. | The theme note states this path was not exercised: the demo student had no enrolable subjects in that database. | **Not executed** | `dev/UI_THEME_IMPLEMENTATION.md` §6 |
| UI-BUILD | Production bundle | build check, outside the four functional levels | `npm run build`. | Build completes. | Reported passed. No build log was archived in this evidence folder. | Pass as a reported build check | `dev/UI_THEME_IMPLEMENTATION.md` §6 |

`npm run lint` is recorded in the same note as still reporting pre-existing project errors. That is not a clean pass of the lint suite, and it is not entered here as a Pass.

## 7. Appendix C — pytest catalogue (the 94 recorded passes)

**Execution:** 2026-10-23, `python -m pytest -q --tb=line` from `backend/`, **94 passed**, 35.10 s, exit 0. Evidence: `backend_pytest.txt`.  
**Build:** the evaluation window above. Individual node ids are not printed; each function below is one of those 94.  
**Database:** testing SQLite, unless a row says it uses a file-backed database.  
**Level key:** unit = no HTTP; integration = Flask test client or route helper with a database.

### Auth, accounts, and access

| Function | Level | Requirement ID | Preconditions and input | Expected result (assertions) | Origin | Narrower than the name? |
|----------|-------|----------------|-------------------------|------------------------------|--------|--------------------------|
| `test_login_schema_validation` | integration | — | POST login with `invalid-email` | 400 and `details` | fixture | No |
| `test_login_invalid_password` | integration | — | Bcrypt user; wrong password | 401 “Invalid email or password” | fixture | No |
| `test_login_success` | integration | — | Teacher user, password `secret123` | 200, token, role and name, no password field | fixture | No |
| `test_register_admin_role_rejected` | integration | — | Admin token; role `admin` | 400 and `details` | fixture | No |
| `test_register_duplicate_email_rejected` | integration | — | Email already stored | 400 “A user with this email already exists” | fixture | No |
| `test_register_student_success` | integration | `FR-AUTH-03`, `NFR-PRIV-02` | Admin registers a student with guardian fields | 201; `created_by` is the admin; `pseudonym_id` set; consent row exists with `consent_given=false` | fixture | No |
| `test_unauthenticated_user_access` | integration | — | GET `/api/admin/users` with no token | 401 | fixture | No |
| `test_login` (`test_rbac.py`) | integration | — | Seed admin `admin@test.com` / `password123` | 200 and token | fixture | Name is only login, and that is what is asserted |
| `test_admin_list_users` | integration | — | Admin token; one student with consent and one teacher | 200; role filter returns that student with consent true; search “Sarah” returns the teacher | fixture | No |
| `test_admin_deactivate_user` | integration | — | Admin PATCH `is_active=false` | 200 and the row is inactive | fixture | No |
| `test_admin_self_deactivation_blocked` | integration | — | Admin PATCH own account | 400 “cannot deactivate their own account” | fixture | No |
| `test_admin_bulk_import_users` | integration | — | CSV of two valid users and one role `principal` | 200; created 2; failed 1; error on row 4 | fixture | No |
| `test_admin_settings_lifecycle` | integration | `FR-ADM-05` | GET settings; PATCH unknown key; PATCH min 300 > max 60; PATCH min 45, max 180, retention 120 | Unknown key 400; min>max 400; valid PATCH 200 with those string values | fixture | Stores bounds. Does not run the intervention engine at 45 s or 180 s |
| `test_non_admin_settings_access_blocked` | integration | — | Student and teacher GET `/api/admin/settings` | Both 403 | fixture | No |
| `test_student_profile_lifecycle` | integration | — | GET profile; PATCH grade, guardian contact, `consent_given=true`, assent | Onboarding completes; grade and guardian contact saved; `consent_given` stays false | fixture | No |
| `test_student_cannot_set_guardian_consent_via_profile` | integration | — | Student PATCH `consent_given=true` | Response 200 with `consent_given=false`; database row stays false | fixture | No |
| `test_non_student_profile_access_blocked` | integration | — | Teacher GET `/api/student/profile` | 403 | fixture | No |
| `test_monitored_session_requires_consent` | integration | — | Enrolled student, no consent row | Monitored start 403 and the error contains “consent required”; unmonitored start 201. The registered handler is `session.py`. `FR-AUTH-06` labels only the unregistered `sessions.py` copy | fixture | No |

### Courses, materials, quizzes

| Function | Level | Requirement ID | Preconditions and input | Expected result (assertions) | Origin | Narrower than the name? |
|----------|-------|----------------|-------------------------|------------------------------|--------|--------------------------|
| `test_get_grade_levels` | integration | — | Seeded grade names | 200; list includes Grade 1 and Grade 2 | fixture | No |
| `test_course_creation_and_ownership` | integration | — | Teacher creates “Mathematics 101” and a module | Subject 201; teacher link exists; module 201; detail lists that module at sequence 1 | fixture | No |
| `test_archive_subject` | integration | — | Teacher archives a subject | `is_archived=true` in response and database; admin can read it; student GET 404 | fixture | No |
| `test_role_based_subject_list_branching` | integration | — | Two teachers, one student | Teacher 1 sees “T1 Subject” only; student sees that same title | fixture | No |
| `test_student_enrollment_lifecycle` | integration | — | Student grade does not match, then matches | Wrong grade 403; enrol 201; duplicate 409; list length 1; drop 200; list length 0 | fixture | No |
| `test_material_file_upload` | integration | `FR-TCH-03` | Teacher uploads `chapter1_guide.pdf` bytes | 201 and `file_url` starts with `/uploads/` | fixture | No |
| `test_quiz_full_lifecycle_and_grading` | integration | — | Teacher quiz: MCQ (electron correct) and short answer “Au” | Create 201; duplicate question ids 400; submit electron + `  au  ` scores 100 and both answers `is_correct`; resubmit 400; second attempt 403; teacher attempt list shows 100 | fixture | Wrong answers are not submitted |
| `test_llm_service_parses_json_pack` | unit | — | `_chat` patched to return one JSON pack | Summary and `correct_option==1` parsed | mocked | Live model not called |
| `test_generate_pack_endpoint_mocked` | integration | — | Route collaborator patched; body includes a description | 200, summary “Generated summary”, one milestone | mocked | Ollama not called |
| `test_create_material_with_milestones` | integration | — | POST material with one milestone, `correct_option=1` | 201; summary stored; one database row | fixture | No |
| `test_manual_trigger_and_milestone_grading` | integration | — | Session with milestones; manual tier 3; answer option 0 | 200 `milestone_quiz`; second trigger 409; response `is_correct is True`; `MilestoneQuestion` stores the answer | injected manual tier | Manual trigger, so cooldown is not under test. Selection among two materials is not under test |

### Monitoring, UNKNOWN, coverage, XP

| Function | Level | Preconditions and input | Expected result (assertions) | Origin | Narrower than the name? |
|----------|-------|-------------------------|------------------------------|--------|--------------------------|
| `test_session_lifecycle_and_telemetry` | integration | Injected DISTRACTED heartbeats; episode backdated to 7 s; engine cooldown forced to 0 and pending cleared | Short episode does not fire; aged episode fires tier 1 `ambient_cue`; response stored; stop reports at least one event and exactly one intervention | injected | Cooldown was cleared in the test |
| `test_heartbeat_with_image_returns_ml_verdict` | integration | Blank JPEG plus client `verdict=FOCUSED`, confidence 0.99 | 200 UNKNOWN, null confidence, `no_face`, `face_detected=false`, `intervention_triggered=false` | synthetic image | Does not return a focused or distracted class |
| `test_heartbeat_unknown_via_corrupt_image` | integration | `data:image/jpeg;base64,AAAA` and client `verdict=FOCUSED` | 200 UNKNOWN, null confidence; observation row state UNKNOWN | synthetic image | No |
| `test_heartbeat_no_face_persists_unknown` | integration | Blank JPEG, no client verdict | UNKNOWN, `no_face`, `face_detected=false`; row matches; no open distraction episode | synthetic image | No |
| `test_predict_invalid_image_is_unknown` | unit | `predict_frame_image("not-valid-base64!!!")` | UNKNOWN, null confidence, reason `no_frame_data` | fixture | No |
| `test_predict_exception_is_unknown_not_focused` | unit | Decode patched; `_infer_frame_signals` raises `RuntimeError` | UNKNOWN, reason `inference_exception`, face_detected is not true | mocked | No |
| `test_predict_no_face_is_unknown_with_face_detected_false` | unit | Blank JPEG through `predict_frame_image` | UNKNOWN, `no_face`, `face_detected=false` | synthetic image | No |
| `test_unknown_closes_open_distraction_episode` | integration | `upsert_distraction_episode` DISTRACTED, then UNKNOWN 5 s later | Open episode exists, then none; closed row has `ended_at` | injected | No |
| `test_episode_gap_breaks_continuity_for_intervention` | integration | DISTRACTED observations at t and t+4 s | First episode ends at t+`T_support`; second starts at t+4; duration at t+5 is about 1 s | injected | No |
| `test_unknown_holds_without_focus_reset` | unit | Engine pending after DISTRACTED; next call state UNKNOWN | Decision is `None`; pending and `last_tier` remain | injected | No |
| `test_unknown_does_not_reset_pending_intervention` | unit | Same, cooldown 30 s; then a FOCUSED call | UNKNOWN keeps pending, tier, and timestamp; FOCUSED clears pending and `last_tier` | injected | No |
| `test_coverage_valid_observations_and_gaps` | unit | F, F, D, F over 20 s | Version set; each bucket positive; buckets sum to 20; unknown at least the gap beyond `T_support` | injected | Exact AN-01 percentages are not asserted |
| `test_coverage_zero_valid_observations_null_focus` | unit | UNKNOWN only, 30 s | Focus null; focused and distracted 0; coverage 0; unknown 30 | injected | No |
| `test_coverage_unmonitored_empty_session` | unit | No observations, 60 s | Focus null; unknown 60; coverage 0 | fixture | No |
| `test_coverage_distracted_gap_unknown_remainder` | unit | D at 0 and 4 s, session 10 s | Distracted 6; focused 0; unknown 4; 4 s is not an interruption gap; 6 s is | injected | No |
| `test_coverage_distracted_then_unknown_clips_support` | unit | D at 0, UNKNOWN at 1, session 10 s | Distracted 1; unknown 9 | injected | No |
| `test_coverage_support_clipped_at_session_end` | unit | FOCUSED at 0, end at 2 s | Focused 2; unknown 0 | injected | No |
| `test_mediapipe_landmarkers_are_session_isolated` | unit | Landmarker factory patched | Two session ids get different objects; clear closes only that session | mocked | No live MediaPipe |
| `test_start_clears_prior_session_landmarker` | integration | Second monitored start after a fake landmarker was attached | New session id; old id removed; `close` called | mocked | No |
| `test_stop_zero_coverage_null_focus_no_focus_xp` | integration | Monitored session backdated 5 minutes, no observations, then stop | Focus null; coverage 0; `xp_gained=0`; metric `observed_v1` | fixture | Zero XP only |
| `test_zero_observed_focused_awards_zero_session_xp` | unit | `observed_focused_seconds=0`, duration 3600, focus null | `xp_gained=0`, `focus_minutes=0` | fixture | Zero XP only |
| `test_repeated_stop_awards_xp_only_once` | integration | 10-minute session; FOCUSED observation every 2 s for 600 s; stop twice | First `xp_gained>0`, metric `observed_v1`, focus not null; second `xp_gained=0`; stored XP unchanged | injected observations | No |
| `test_claim_session_xp_award_is_atomic` | integration | File-backed SQLite; 8 threads call `claim_session_xp_award` | Exactly one True and seven False; `xp_awarded=true` | fixture | Claim flag only; XP amount not awarded in this test |
| `test_xp_claim_and_award_rollback_then_retry` | integration | File-backed SQLite; `award_session_xp` patched to raise once; `observed_focused_seconds=120` | Failed attempt leaves `xp_awarded=false` and `xp_gained=0`; retry returns `xp_gained>0` and `xp_awarded=true` | mocked failure, then real award | The failure is a patched exception |
| `test_claim_session_xp_award_commit_false_stays_uncommitted_until_outer` | integration | `claim_session_xp_award(..., commit=False)` then rollback | Claim returns true; after rollback `xp_awarded=false` | fixture | No |
| `test_award_session_xp_and_first_badge` | unit | `duration_seconds=600`, `focus_percentage=80`, no observed seconds | 8 focus minutes, 16 XP, streak 1, badge `first_session` | fixture | Legacy formula, not `observed_v1` |
| `test_award_quiz_ace` | unit | 5 of 5 correct | `quiz_ace` true; XP 5×10+25; badge `quiz_ace` | fixture | No |
| `test_progress_endpoints` | unit call plus integration GET | Legacy `award_session_xp` for 3600 s at 100% focus, then GET progress and badges | Progress XP and focus minutes positive; badge `focus_60` earned; badges list non-empty | fixture | Uses the legacy XP branch |
| `test_ui_preferences_patch` | integration | PATCH profile `theme=calm-dark`, `textSize=l`, `reduceMotion=true`, assent | 200; response preferences echo `calm-dark`; assent and onboarding true | fixture | Response body only; no second GET and no pixels |
| `test_analytics_endpoints` | integration | Legacy distraction event of 50 s inside a 100 s session, no `observed_v1` snapshot | Teacher, student, and admin analytics 200; focus averages are **null**, not 50% | fixture | No |

### Intervention engine and noise

| Function | Level | Preconditions and input | Expected result (assertions) | Origin |
|----------|-------|-------------------------|------------------------------|--------|
| `test_distraction_level_bands` | unit | Durations 3, 5, 12, 25, 45 s | Levels 0, 1, 2, 3, 4 | fixture |
| `test_tier1_ambient_after_mild_duration` | unit | Episode age 7 s, cooldown 0 | Tier 1 `ambient_cue` | injected episode |
| `test_cooldown_suppresses_repeat` | unit | Cooldown **60 s**. Fire at t=100. Pending check at t=130. `record_outcome("reengaged")`. Again at t=130. Again at t=165 | First decision exists; both t=130 calls are `None`; t=165 returns tier 1 | injected |
| `test_ignored_escalates_one_tier` | unit | Cooldown 0; outcome `ignored` | Next decision is tier 2 pacing | injected |
| `test_quiz_context_uses_hint_injection` | unit | Episode 25 s, quiz context, cooldown 0 | Tier 3 hint type; payload contains `hint_text` | injected |
| `test_content_context_uses_milestone_quiz` | unit | Episode 25 s, not a quiz, cooldown 0 | Type is milestone quiz | injected |
| `test_tier4_pacing_then_suggest_break` | unit | Episode 50 s; then `ignored` | First pacing-reduction; second suggest-break | injected |
| `test_disabled_tier_falls_back` | unit | Enabled tiers {1, 2}; episode 50 s | Tier 2 pacing, not tier 4 | injected |
| `test_all_tiers_disabled_fires_nothing` | unit | `enabled_tiers=[]`; episode 50 s | Enabled set is empty; decision is `None` | injected |
| `test_get_enabled_tiers_preserves_empty_config` | integration | Subject config with all four flags false | `_get_enabled_tiers` returns `[]` | fixture |
| `test_focus_resets_escalation` | unit | Ignored tier 1, then state FOCUSED | Decision `None` and `last_tier is None` | injected |
| `test_sustained_background_noise_triggers_one_time_notice` | integration | Injected `verdict=FOCUSED`; noise dBFS samples. Lesson-audio sample must not set a baseline. Five quiet samples at −50. Four loud samples at −30 | Fourth loud beat fires one `environment_noise_notice`; verdict stays FOCUSED; no distracted episode; headphones action stored; a later loud run does not fire; stop drops the monitor | injected verdict and levels |
| `test_baseline_is_median_of_first_five_samples` | unit | Levels −40, −60, −50, −55, −45 | Uncalibrated until the fifth; baseline −50 | fixture |
| `test_single_spike_does_not_fire_and_quiet_sample_resets_streak` | unit | Three loud, one quiet, three loud | No fire | fixture |
| `test_four_sustained_loud_beats_fire` | unit | Calibrated at −50; four samples at −30 | Only the fourth returns true | fixture |
| `test_unmarked_detection_stays_pending_so_it_is_not_lost` | unit | Four loud samples, notice not marked shown, then a quiet sample | Quiet sample still returns true; `notice_shown` false | fixture |
| `test_notice_never_fires_again_after_being_shown` | unit | Fire once, `mark_notice_shown`, then louder samples | All later updates false | fixture |
| `test_lesson_audio_samples_are_ignored` | unit | Loud samples with `lesson_audio_active=true` | No calibration and no streak | fixture |
| `test_missing_mic_samples_are_ignored` | unit | `update(None)` | False; not calibrated | fixture |
| `test_already_loud_room_fires_once_after_calibration` | unit | Five samples at −15, then mark shown | Fifth is true; later loud samples false | fixture |
| `test_consider_noise_fires_tier1_notice_without_touching_visual_state` | unit | `consider_noise` at −25 against baseline −50 | Tier 1 noise notice; `last_tier` stays none | fixture |
| `test_consider_noise_blocked_by_pending_and_cooldown` | unit | Cooldown 30 s | Second call while pending is `None`; after outcome, t+10 is `None`; t+31 fires | fixture |
| `test_ignored_noise_cue_does_not_escalate_next_visual_intervention` | unit | Noise notice recorded as ignored, then an 8 s visual episode | Next visual tier is 1 | injected |
| `test_consider_noise_respects_disabled_tier1` | unit | Enabled tiers {2, 3, 4} | `consider_noise` returns `None` | fixture |
| `test_heartbeat_schema_accepts_and_bounds_noise_fields` | unit | `noise_dbfs=-42.5`; then `5.0` | Accepts −42.5; 5.0 raises `ValidationError` | fixture |
| `test_intervention_response_schema_validates_noise_action` | unit | `noise_action="Headphones"`; omitted; `"ignore_it"` | Stored lowercase `headphones`; omitted is null; unknown value raises | fixture |
| `test_trigger_milestone_quiz_intervention` | integration | Manual tier 3 on a monitored session | 200, triggered, tier 3, type `milestone_quiz`, payload contains `milestone_question_id` | injected manual tier |

`test_trigger_milestone_quiz_intervention` does not submit an answer, so it does not grade. It also does not compare two materials.

### Script guards and CSV import

| Function | Level | Expected result | Origin |
|----------|-------|-----------------|--------|
| `test_fusion_video_has_no_filename_probability_override` | unit | `models/test_fusion_video.py` does not contain the old filename probability overrides | source text |
| `test_run_tests_fusion_summary_defines_threshold_f1` | unit | `models/run_tests.py` contains `f1_thr` and does not contain the unbound `{f12}` format | source text |
| `test_parse_and_validate_csv_valid` | unit | Two data rows valid; roles, grade, guardian, and row numbers kept | fixture CSV |
| `test_parse_and_validate_csv_validation_errors` | unit | Bad email and missing guardian → 0 valid, 2 errors | fixture CSV |
| `test_parse_and_validate_csv_duplicate_email_in_file` | unit | Duplicate rows rejected; the third email kept | fixture CSV |
| `test_parse_and_validate_csv_grade_level_validation` | unit | `Grade 10` kept; `Grade10` rejected | fixture CSV |
| `test_parse_and_validate_csv_none_value_safety` | unit | Malformed text returns an error list | fixture |
| `test_parse_and_validate_csv_binary_file_safety` | unit | JPEG bytes → 0 valid rows and a missing-email-header error | fixture |

These two script guards read source text. They do not execute the fusion model.

## 8. Appendix D — tests present in the tree and not in the recorded 94

| Function | Level | What the source asserts | Status |
|----------|-------|-------------------------|--------|
| `test_ensure_default_data_creates_accounts_and_is_idempotent` | integration | Empty database gains 3 accounts and 12 grades; second call creates nothing; bcrypt and guardian consent checked | **Not executed** |
| `test_default_student_can_login` | integration | After seeding, `student@luma.com` login returns 200, a token, and role student | **Not executed** |
| `test_create_app_testing_does_not_auto_seed` | unit | Testing config has `SEED_DEFAULT_ACCOUNTS` false and zero users | **Not executed** |

File: `backend/tests/test_default_accounts.py`. No result from 2026-10-23 includes these names. They are not marked Pass.

## 9. Counts (do not add families together)

| Family | Pass | Fail | Not executed |
|--------|------|------|----------------|
| Harness Run 1 | 27 | 2 (TE-02, AD-01) | 2 (MON-04, ST-06) |
| Harness Run 2 | 29 | 0 | 2 (MON-04, ST-06) |
| Browser BR-01–BR-04 | 4 | 0 | 0 |
| Phase 2A browser items 3 and 4 | 2 | 0 | 0 |
| Theme settings screenshots | 1 record, settings and listed chrome | 0 | Lesson / quiz / intervention theme path |
| Pytest recorded on 2026-10-23 | 94 | 0 | — |
| `test_default_accounts.py` | 0 | 0 | 3 |
