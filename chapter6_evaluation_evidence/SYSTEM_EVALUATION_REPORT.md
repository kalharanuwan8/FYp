# System-level evaluation report — Luma (Chapter 6)

**Evaluation date:** 2026-10-23  
**Evidence folder:** [dev/test_outputs/system_evaluation/2026-10-23/](test_outputs/system_evaluation/2026-10-23/)  
**Thesis bundle:** [chapter6_evaluation_evidence/](../chapter6_evaluation_evidence/) (copied artifacts)  
**Scope:** Integrated workflows, intervention behaviour, access controls, observation accounting (`observed_v1`), and responsiveness.  
**Out of scope:** Model retraining and model-accuracy evaluation. No claims of improved attention, learning outcomes, or classification accuracy.

Normative references: [SYSTEM.md](../SYSTEM.md), [PHASE_1_FIX_REPORT.md](PHASE_1_FIX_REPORT.md), [PHASE_2A_FIX_REPORT.md](PHASE_2A_FIX_REPORT.md), [OBSERVATION_COVERAGE_SPEC.md](OBSERVATION_COVERAGE_SPEC.md).

---

## 1. Evaluated configuration

| Item | Value |
|------|-------|
| Branch | `camtesting` |
| HEAD | `b6ea923ff1819ef12212456ad5295726f3147b24` |
| Phase 2A code commit | `6b1d6541fc551a367038b569f18db1904c7df481` |
| Uncommitted changes | **Yes** — UI theme files remain unstaged (see `git status`). This tree is **not** described as fully frozen. The commit alone **cannot reproduce the evaluated interface**. |
| OS | Windows 11 Pro 10.0.26200 |
| CPU / RAM | Intel i7-13620H / 16 088 MB |
| GPU | NVIDIA GeForce RTX 4050 Laptop GPU; Intel UHD Graphics |
| Python / Torch | 3.12.5 / 2.5.1+cu121 (`cuda=True`) |
| Inference service | Checkpoints load with `ml_mode=full` (weights present at init). MediaPipe/TFLite also logs CPU XNNPACK. |
| Heartbeat interval | 2000 ms (`useMonitoringSession` default) |
| Coverage metric | `observed_v1` (`T_support=3.0` s; `T_gap_max=5.0` s) |
| Checkpoint hashes | Match [BASELINE_CHECKPOINT_HASHES.md](BASELINE_CHECKPOINT_HASHES.md) (recomputed 2026-10-23) |

Full machine-readable config: [evaluated_configuration.json](test_outputs/system_evaluation/2026-10-23/evaluated_configuration.json).

### Input modes (by test family)

| Mode | Used for |
|------|----------|
| Flask test-client blank JPEG | UNKNOWN / no_face heartbeats; request-processing timing |
| TESTING verdict injection | Controlled DISTRACTED/UNKNOWN pathway |
| Manual `trigger-intervention` | Tier UI types, pending lock, disabled-tier fallback (**bypasses duration/cooldown**; pending lock still enforced) |
| Browser + canvas `getUserMedia` mock | Playback / DemoPanel interventions; analytics UI |
| Real camera | **Not executed** |

---

## 2. Method summary

1. **Automated harness** (`run_system_evaluation.py`) against Flask `testing` app with isolated `*@luma.demo` accounts.  
2. **Independent analytics** — expected numeric values computed by hand from OBSERVATION_COVERAGE_SPEC arithmetic; actual values from `compute_coverage_from_observations` (not used to generate expected).  
3. **Backend regression** — full `pytest` suite (no silent product fixes during measured runs).  
4. **Browser demos** — Cursor IDE browser; mocked camera; DemoPanel Ctrl+Shift+D.  
5. **Harness corrections** — Run 1 failed TE-02 (wrong URL) and AD-01 (missing guardian fields / duplicate email). **Product code unchanged.** Harness fixed; **Run 2** recorded separately.

Family totals below are **not** unique-test counts and must not be added together (harness vs browser are separate families with overlapping concerns).

---

## 3. Results summary

| Source | Pass | Fail | Not executed |
|--------|------|------|--------------|
| Harness Run 1 (preserved) | 27 | 2 | 2 |
| Harness Run 2 (after harness-only fixes) | **29** | **0** | **2** |
| Browser integration (BR-01–BR-04) | **4** | **0** | — |
| Not executed (camera denial UX ST-06; real camera MON-04) | — | — | **2** |
| Backend pytest | **94** | 0 | — |

Harness Run 2 machine summary: [logs/evaluation_results.json](test_outputs/system_evaluation/2026-10-23/logs/evaluation_results.json).  
Run 1 preserved: [logs/evaluation_results_run1.json](test_outputs/system_evaluation/2026-10-23/logs/evaluation_results_run1.json).

---

## 4. Test catalogue

Status values: **pass** / **fail** / **not_executed**.  
Kinds: automated | controlled_input | browser | real_camera | manual_demo.

### 4.1 Student workflow

| ID | Requirement | Procedure | Expected | Actual | Status | Evidence | Kind |
|----|-------------|-----------|----------|--------|--------|----------|------|
| ST-01 | Login | `POST /api/auth/login` | 200 + token | 200 + token | pass | api_samples/st01_login.json | automated |
| ST-02 | Enrolment access | `GET /my-enrollments` | 200 | 200 | pass | api_samples/st02_enrollments.json | automated |
| ST-03 | Open material metadata | GET subject/module | 200 | 200 | pass | api_samples/st03_material.json | automated |
| ST-04 | Quiz attempt/submit | attempt + submit | attempt created; submit accepted | attempt **201** (`attempt_id=1`); submit **200**. Sample does **not** include score/correctness | pass | api_samples/st04_quiz.json | automated |
| ST-05 | Preference persistence | PATCH/GET profile | theme persisted | sage persisted | pass | — | automated |
| ST-06 | Camera denial UX | Deny getUserMedia | session does not start | Not run in automation | **not_executed** | logs/not_executed.txt | browser |
| BR-01 | Student dashboard demo | Login demo.phase2a | Dashboard loads | Loaded | pass | screenshots/01_student_dashboard.png | browser |

### 4.2 Monitoring

| ID | Requirement | Procedure | Expected | Actual | Status | Evidence | Kind |
|----|-------------|-----------|----------|--------|--------|----------|------|
| MON-01 | Heartbeat + UNKNOWN | blank JPEG | UNKNOWN, no_face, conf null, face_detected false | start 201; hb 200; `verdict=UNKNOWN`, `reason=no_face`, `confidence=null`, `face_detected=false`, `ml_mode=full` (checkpoints **loaded**; no-face path returns UNKNOWN without a usable fusion classification) | pass | api_samples/mon01_heartbeat.json | controlled_input |
| MON-02 | Session ownership | other student heartbeat | 403/404 | forbidden | pass | — | automated |
| MON-03 | Stop + repeat stop | stop twice | coverage fields; XP not double-awarded | 200; `focus_metric_version=observed_v1` | pass | api_samples/mon03_stop.json | automated |
| MON-04 | Real-camera smoke | Physical webcam | live usable verdicts | — | **not_executed** | logs/not_executed.txt | real_camera |

### 4.3 Interventions

| ID | Requirement | Procedure | Expected | Actual | Status | Evidence | Kind |
|----|-------------|-----------|----------|--------|--------|----------|------|
| INT-01 | Pending lock | Manual T1 then T2 | 409 while pending; T2 after response | ambient then 409 then pacing | pass | api_samples/int01_manual_pending.json | controlled_input |
| INT-02 | Milestone response recorded | Manual T3 + option + response | response accepted | T3 **200** (`milestone_quiz`); response **200** with `user_response=reengaged`, `message=Intervention response recorded successfully`; `is_correct=null` in sample (no graded-correct claim) | pass | Run 2 `evaluation_results.json` INT-02 | controlled_input |
| INT-03 | Disabled tier | Disable tier2; **new session**; trigger 2 | fallback ≠ pacing_pause | ambient_cue | pass | — | controlled_input |
| INT-04 | Normal decision pathway (duration band) | Controlled DISTRACTED + aged episode; fixture **cooldown=0** | may fire ambient from open-episode duration | **200**; `intervention_triggered=true`; `intervention_type=ambient_cue`. Does **not** establish 30 s cooldown enforcement | pass | api_samples/int04_controlled_pathway.json | controlled_input |
| INT-05 | UNKNOWN hold | UNKNOWN heartbeat | no escalation | triggered false | pass | — | controlled_input |
| BR-02 | Ambient leaves playback | DemoPanel T1 | playing continues | playing=true; one click→DOM observation ~996 ms (not a general latency estimate) | pass | intervention_display_timing.csv | browser |
| BR-03 | Pacing pauses playback | DemoPanel T2 after dismiss | video paused | paused=true | pass | intervention_display_timing.csv | browser |

**Note on manual triggers:** `POST …/trigger-intervention` bypasses episode-duration bands and cooldown, but still respects the one-pending lock and enabled-tier fallback. INT-04 uses the normal `decide_intervention` path with controlled observations and **cooldown=0** in the eval fixture, so it only demonstrates duration-band triggering under zero cooldown.

**Cooldown enforcement (unit evidence, not INT-04):** [`test_cooldown_suppresses_repeat`](../backend/tests/test_intervention_engine.py) in `backend/tests/test_intervention_engine.py` constructs `InterventionEngine(cooldown_seconds=60.0)`, fires once at `now=100`, after `record_outcome("reengaged")` still returns `None` at `now=130` (inside cooldown), then fires again at `now=165` (after cooldown). Pending-lock blocking without outcome is also asserted in that test and by INT-01 (HTTP 409).

Teacher config is loaded when the session engine is built — changing tiers requires a **new session** (INT-03).

### 4.4 Teacher / administrator

| ID | Requirement | Procedure | Expected | Actual | Status | Evidence | Kind |
|----|-------------|-----------|----------|--------|--------|----------|------|
| TE-01 | Create subject | POST subject | 201/200 create | **201**; body keys include `id`, `title`, `grade_level_id`, `is_archived`, timestamps | pass | Run 2 results TE-01 | automated |
| TE-02 | Review/save milestones | GET/PATCH materials/:id | 200 + milestones | 200 (Run 2) | pass | api_samples/te02_milestones.json | automated |
| TE-03 | Generate pack / error handling | POST generate-pack | useful error if unavailable/invalid | **400** `Validation failed`; details: `description` field required; pack **not** generated | pass | api_samples/te03_generate_pack.json | automated |
| TE-04 | Intervention config | GET/PATCH config | 200 | 200 | pass | — | automated |
| AD-01 | Create + deactivate | register + status | 201 + 200 | OK (Run 2; unique email + guardian fields) | pass | — | automated |
| AD-02 | Consent gate | no-consent monitored start | 403 | 403 | pass | — | automated |
| AD-03 | Student cannot PATCH consent | student PATCH consent | 403 | 403 | pass | — | automated |
| AD-04 | Wrong-role admin API | student GET /admin/users | 403 | 403 | pass | — | automated |

### 4.5 Analytics (independent expected values)

| ID | Requirement | Procedure | Expected (hand) | Actual | Status | Evidence | Kind |
|----|-------------|-----------|-----------------|--------|--------|----------|------|
| AN-01 | Mixed F/D | F@0,F@2,D@10,F@12; 20 s | F=8,D=2,U=10,focus=80%,cov=50% | match | pass | logs/analytics_fixtures.json | controlled_input |
| AN-02 | Gap remainder | D@0,D@4; 10 s | D=6,U=4,focus=0%,cov=60% | match | pass | same | controlled_input |
| AN-03 | Zero coverage | UNKNOWN only; 30 s | focus null, cov 0 | match | pass | same | controlled_input |
| AN-04 | End clip | F@0; end 2 s | F=2,U=0 | match | pass | same | controlled_input |
| AN-05 | Empty session | no obs; 60 s | focus null, U=60 | match | pass | same | controlled_input |
| AN-06 | Legacy not mixed into observed_v1 aggregates | analytics with legacy row (`focus_percentage=88`, `focus_metric_version=None`) present | 200; average not dominated by legacy 88 | **200**; `focus_metric_version=observed_v1`, `avg_focus_percentage=0.0`, `avg_monitoring_coverage_pct=18.3` (not ~88). Aggregates in `average_focus_percentage` / `average_coverage_pct` only include `focus_metric_version == observed_v1` | pass | api_samples/an06_analytics.json | automated |
| AN-07 | Zero focus XP | observed_focused_seconds=0 | xp_gained=0 | 0 | pass | — | controlled_input |
| BR-04 | UI shows focus + coverage | Progress/analytics page | both shown | 0% average focus · 3% monitoring coverage | pass | screenshots/03_student_analytics.png | browser |

---

## 5. Responsiveness

### 5.1 Flask test-client heartbeat request-processing time (PERF-01)

**Label:** Flask test-client **request-processing time** for blank-JPEG heartbeats that resolve to UNKNOWN/`no_face`.  
**Not** full-pipeline inference latency. **Not** end-to-end browser telemetry latency. **Not** distraction-detection latency (no labelled onset). **Not** the configured 2000 ms heartbeat interval.

**Condition:** Flask test client; blank JPEG; CUDA available in process; service reports `ml_mode=full` at init (checkpoints **loaded**). On this no-face path the API returns UNKNOWN without establishing that every loaded model executed a usable classification.

**Timer includes:** request handling + route + work performed on the no-face path + DB write.  
**Timer excludes:** browser capture, network transport, React render.

| Metric | Value |
|--------|-------|
| Cold / first request | 163.98 ms |
| Steady samples | 35 |
| Failures | 0 |
| Median (steady) | 34.38 ms |
| 95th percentile (steady) | 42.08 ms |
| Min / max (steady) | 30.44 / 47.17 ms |

Raw CSV: [heartbeat_rtt.csv](test_outputs/system_evaluation/2026-10-23/heartbeat_rtt.csv).

### 5.2 Intervention display (browser)

**Timer:** DemoPanel tier button click → first matching overlay text in DOM.  
**Includes:** HTTP path used by the UI + React commit.  
**Excludes:** Human reaction time; camera pipeline.

| Event | Result |
|-------|--------|
| Ambient (T1) | Overlay ~996 ms (**one** click→DOM observation; not a general latency estimate); playback continued |
| Pacing (T2) | Playback paused (`video.paused=true`); overlay-text poll incomplete in one run |

CSV: [intervention_display_timing.csv](test_outputs/system_evaluation/2026-10-23/intervention_display_timing.csv).

---

## 6. Backend suite

| Run | Path | Result |
|-----|------|--------|
| Full pytest | [logs/backend_pytest.txt](test_outputs/system_evaluation/2026-10-23/logs/backend_pytest.txt) | **94 passed**, ~35 s, exit 0 |

Includes `test_cooldown_suppresses_repeat` (60 s cooldown assertions above). No product defects were silently fixed during this measured suite run.

---

## 7. Known defects and evaluation limitations

1. **Train/serve mismatch** remains; this evaluation does **not** validate live fusion generalisation or claim accuracy.  
2. **Real camera** (MON-04) and **camera-denial UX** (ST-06) were **not executed**.  
3. **Uncommitted UI theme files** exist on the branch; the commit alone **cannot reproduce the evaluated interface**.  
4. Heartbeat timings are **Flask test-client request-processing times** on the blank/no-face path — not full-pipeline inference latency and not end-to-end browser telemetry latency. `ml_mode=full` means checkpoints were loaded, not that every model ran on that path.  
5. Manual intervention triggers bypass duration/cooldown by design. INT-04 demonstrates duration-band firing under **cooldown=0** only; **30 s cooldown enforcement** is covered by unit test `test_cooldown_suppresses_repeat`, not by INT-04.  
6. The ~996 ms ambient display figure is a **single** DemoPanel click→DOM observation, not a general latency estimate.  
7. Ollama availability is environment-dependent; TE-03 recorded a **400** validation error (`description` required), not a successful pack generation.  
8. Harness Run 1 TE-02/AD-01 failures were **harness/procedure errors**, not product regressions (corrected in Run 2 without changing application code).

---

## 8. Concise factual summary (for Chapter 6)

On 2026-10-23, Luma was evaluated on Windows 11 with Phase 2A accounting committed (`6b1d654` / HEAD `b6ea923`) and uncommitted theme UI still present, so the commit alone cannot reproduce the evaluated interface. Using isolated demo accounts, automated API tests and controlled observation fixtures verified student login/enrolment, quiz attempt creation and submit acceptance, session stop with `observed_v1` fields, UNKNOWN handling for blank/no-face frames, session ownership, consent and RBAC gates, intervention pending locks and disabled-tier fallback (new session after config change), and independent `observed_v1` coverage arithmetic (including null focus at zero coverage and zero focused-time XP). A legacy session with 88% focus was not reflected as ~88% in the student analytics average labelled `observed_v1`. Browser checks with a mocked camera (BR-01–BR-04) confirmed ambient cues leave lesson playback running and pacing pauses playback; the analytics UI showed focus percentage and monitoring coverage together. Steady-state Flask test-client request-processing times for blank-JPEG (no-face) heartbeats were median 34.38 ms and p95 42.08 ms over 35 requests after separating a colder first request; these are not full-pipeline inference latency. INT-04 used cooldown=0 and does not prove 30-second cooldown enforcement (unit test `test_cooldown_suppresses_repeat` does). Real-camera smoke testing and camera-denial UX were not executed. The ~996 ms ambient overlay figure is one click-to-DOM observation. The full backend suite reported 94 passed. This evaluation does not measure or claim model accuracy or learning outcomes.

---

## 9. Evidence index

| Path | Contents |
|------|----------|
| `evaluated_configuration.json` | Config snapshot |
| `REPRODUCTION.md` | Commands + fixture IDs |
| `logs/evaluation_results.json` | Harness Run 2 results |
| `logs/evaluation_results_run1.json` | Harness Run 1 (2 harness fails) |
| `logs/backend_pytest.txt` | Full suite |
| `logs/analytics_fixtures.json` | Independent coverage cases |
| `heartbeat_rtt.csv` | Test-client request-processing samples |
| `intervention_display_timing.csv` | Browser intervention timers |
| `api_samples/*.json` | Sanitised API bodies (no tokens/passwords) |
| `screenshots/*.png` | Demo-data UI captures |
| `run_system_evaluation.py` | Harness source |
| `../../chapter6_evaluation_evidence/` | Thesis-ready copy of the above |

---

*End of system evaluation report.*
