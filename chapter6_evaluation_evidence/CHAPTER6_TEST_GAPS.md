# Chapter 6 coverage and gaps — Luma

**Prepared:** 2026-10-24, from the catalogue in [CHAPTER6_TEST_CASES.md](CHAPTER6_TEST_CASES.md).  
**Rule:** a behaviour already asserted by a recorded test is not listed again as a new test. Rows below that were not run stay **Not executed**. None of them is a Pass.

The seven headings are the behaviours the chapter is likely to claim. Under each heading, “Already recorded” is the evidence that exists. “Still open” is the remainder.

## Priority

| Priority | ID | Open check | Why it is still open | Status |
|----------|----|------------|----------------------|--------|
| P1 | G-CAM-DENY | Deny the camera in the browser and confirm the monitored session does not start | ST-06 was not executed. BR-01–BR-04 used a canvas mock | **Not executed** |
| P1 | G-CAM-LIVE | Physical webcam: a face yields a non-UNKNOWN verdict, and leaving the frame yields UNKNOWN | MON-04 was not executed. Blank JPEGs only show the no-face path | **Not executed** |
| P1 | G-LLM-503 | Generate-pack with a real `description` while Ollama is unreachable | TE-03 is HTTP 400 for a missing field. The 503 branch was not called | **Not executed** |
| P2 | G-TIER-ALL | All four subject tier flags off, then a **new** session, then an aged DISTRACTED heartbeat | Unit test and route helper exist separately. INT-03 disables only tier 2 and uses the manual trigger | **Not executed** |
| P2 | G-COOL-30 | Heartbeat path just inside and just after the session cooldown of 30 s | `test_cooldown_suppresses_repeat` uses 60 s on the engine object. INT-04 set cooldown to 0 | **Not executed** |
| P2 | G-QUIZ-WRONG | Submit a wrong multiple-choice option and a wrong short answer | The recorded quiz test submits a correct paper only | **Not executed** |
| P2 | G-MILESTONE-WHICH | Two materials in one module, with different questions | No test distinguishes which item is served. The picker is module-wide | **Not executed** |
| P2 | G-THEME-RELOAD | Sign out and in again; stored theme is applied on `<html>` | ST-05 and the preferences pytest check JSON. Screenshots are same-session settings | **Not executed** |
| P2 | G-THEME-LESSON | Calm dark (or another non-default theme) on the lesson, quiz, and intervention screens | Theme note: that path was not opened, because the demo student had nothing to enrol | **Not executed** |
| P3 | G-COOL-EQ | Decision at exactly `last_intervention_at + cooldown` | The 60 s test uses t=130 (inside) and t=165 (after), not the equal instant | **Not executed** |
| P3 | G-LLM-BADJSON | Model returns non-JSON | Parser is tested with valid JSON only. Route mapping of that error was not called | **Not executed** |
| P3 | G-THEME-MOTION | Text size and reduce-motion change the learning UI | The pytest stores the preference values. No visual check was archived | **Not executed** |

## 1. Camera permission denial and physical-camera operation

### Already recorded

| Evidence | What it shows | What it leaves out |
|----------|---------------|--------------------|
| ST-06 | Status **Not executed** | Denial UX |
| MON-04 | Status **Not executed** | A physical webcam |
| MON-01, `test_predict_no_face_is_unknown_with_face_detected_false`, `test_heartbeat_no_face_persists_unknown`, `test_heartbeat_with_image_returns_ml_verdict` | A synthetic blank JPEG becomes UNKNOWN / `no_face` / `face_detected=false` | A lens, a permission prompt, or a face |
| `test_heartbeat_unknown_via_corrupt_image`, `test_predict_invalid_image_is_unknown`, `test_predict_exception_is_unknown_not_focused` | Corrupt base64, invalid data, and a raised inference error become UNKNOWN | A device |
| BR-01–BR-04, P2A-BR-3, P2A-BR-4 | Cursor browser with a **mocked** `getUserMedia`. P2A-BR-4 releases that mock stream on stop | Denial, and a physical camera |
| `useMonitoringSession.js` `startCamera` | On failure it sets `cameraError` to the allow-camera message, sets `cameraActive` false, and returns false. A mic failure retries video-only | This is source, not a recorded run |

`dev/test_outputs/system_evaluation/2026-10-23/logs/not_executed.txt` says these two cases were done in the browser section. The harness JSON and the browser note do not. They stay **Not executed**.

### Still open

**G-CAM-DENY (manual, physical or browser permission UI).** Do not automate a fake `getUserMedia` rejection and then cite it as this check; the mock path is already how BR-02 was run.

1. Use Chrome or Edge on the evaluation machine, signed in as a consented demo student who is enrolled on a subject with a video (`demo.phase2a@luma.com` after `backend/seed_phase2a_demo.py`, or an equivalent consented student).
2. Open the lesson player that starts monitoring.
3. When the browser asks for the camera, choose **Block** / Don’t allow. If the permission is already stored, reset it for `http://localhost:5173` in the site settings, then reload.
4. Expected, from the current `startCamera` catch path: the allow-camera message is shown, the camera is not active, and a monitored session does not proceed to the heartbeat loop. Record the on-screen text and whether `POST /api/session/start` with `is_monitored=true` was sent (network panel).
5. Reload, allow the camera, and confirm a preview appears. That second half is G-CAM-LIVE if it is the same sitting.
6. Write the outcome as Pass or Fail only after this sitting. Until then the status is **Not executed**.

**G-CAM-LIVE (manual, physical webcam).**

1. Same consented student and lesson. Allow the camera. Sit with light on the face, looking at the screen, for at least three heartbeat intervals (the client interval used in the evaluation was 2000 ms).
2. Record three heartbeat responses: `verdict`, `reason`, `face_detected`, `confidence`, `ml_mode`. A usable face should not be `reason=no_face`.
3. Cover the lens, or leave the frame, for at least three further heartbeats. Expected from the blank-frame tests: `verdict=UNKNOWN`, `reason=no_face`, `face_detected=false`, `confidence=null`. This sitting is what would connect that expectation to a real sensor. The blank JPEG tests do not substitute for it.
4. Stop the session and confirm the camera indicator goes off (P2A-BR-4 did this only for the mock stream).
5. Do not claim classification accuracy. The evaluation scope excludes model accuracy.

## 2. UNKNOWN handling and interruption of distraction episodes

### Already recorded

| Evidence | Assertion that is already in the result |
|----------|------------------------------------------|
| MON-01 and the blank-JPEG pytest rows | No face → UNKNOWN, and the client cannot force FOCUSED by sending that verdict with the image |
| `test_unknown_closes_open_distraction_episode` | A DISTRACTED episode is open, then an UNKNOWN update leaves no open episode and sets `ended_at` |
| `test_coverage_distracted_then_unknown_clips_support` | DISTRACTED at 0 s and UNKNOWN at 1 s → 1 s distracted and 9 s unknown |
| `test_episode_gap_breaks_continuity_for_intervention` | A 4 s gap closes the first episode at `T_support` and opens a new one whose duration does not swallow the gap |
| `test_unknown_holds_without_focus_reset`, `test_unknown_does_not_reset_pending_intervention` | UNKNOWN does not clear a pending intervention or `last_tier`; FOCUSED does |
| INT-05 | An UNKNOWN heartbeat returns `intervention_triggered=false` |
| P2A-BR-3 | The demo panel shows UNKNOWN for synthetic blank frames |
| AN-03 | An UNKNOWN-only session has null focus and zero coverage |

### Still open

No second engine test is required for “UNKNOWN closes an episode” or “UNKNOWN does not escalate”. Those assertions exist.

The open remainder is physical, and it is G-CAM-LIVE step 3: the same UNKNOWN fields when a real face leaves the frame during a session that already has an open DISTRACTED episode. INT-05 does not record `ended_at`. The episode-close test does not go through the camera. One physical sitting can note both the verdict and whether the open episode closes; that note is still **Not executed**.

## 3. All intervention tiers disabled, and cooldown boundaries

### Already recorded

| Evidence | Assertion |
|----------|-----------|
| `test_all_tiers_disabled_fires_nothing` | `enabled_tiers=[]` stays empty; a 50 s episode returns `None` |
| `test_get_enabled_tiers_preserves_empty_config` | All four subject flags false → helper returns `[]` |
| `test_disabled_tier_falls_back` | Tiers {1, 2} only; a level-4 episode falls back to tier 2 pacing |
| `test_consider_noise_respects_disabled_tier1` | Noise notice does not fire when tier 1 is off |
| INT-03 | Tier 2 off, **new** session, **manual** trigger 2 → `ambient_cue` |
| `test_cooldown_suppresses_repeat` | Engine cooldown 60 s: fire at t=100; pending blocks; after `reengaged`, t=130 is still `None`; t=165 fires tier 1 |
| `test_consider_noise_blocked_by_pending_and_cooldown` | Noise helper, cooldown 30 s: blocked while pending and at t+10 after an outcome; fires at t+31 |
| `test_admin_settings_lifecycle` | `FR-ADM-05` keys: min 300 with max 60 is rejected; min 45, max 180, retention 120 are stored |
| INT-01 | Manual trigger: pending lock is HTTP 409. Duration and cooldown are skipped by that route |
| INT-04 | Injected DISTRACTED episode fires `ambient_cue` while the fixture cooldown is 0 |
| `test_session_lifecycle_and_telemetry` | Aged injected episode fires tier 1 after the test sets cooldown to 0 and clears pending |

The engine default in `InterventionEngine` is `cooldown_seconds=30.0`. The recorded suppression test constructs **60.0**. Citing the 60 s test as “the 30 s rule was measured” would over-claim. Citing it as “a cooldown window suppresses a repeat and a later time allows one” matches the assertions.

### Still open

**G-TIER-ALL.** The empty list is tested on the engine, and the empty config is tested on the helper. Nothing recorded starts a monitored session from a subject whose four flags are false and then sends an aged DISTRACTED heartbeat. INT-03 must not be cited for this. Suggested sitting, still **Not executed**:

1. As the teacher, set tier 1–4 off for one subject and save.
2. As a consented student, start a **new** monitored session on that subject (the engine reads config at start).
3. Inject or produce a DISTRACTED episode older than 10 s.
4. Expected if the two existing tests compose: no intervention payload. Record the heartbeat JSON.
5. Turn the tiers back on and start another new session if a positive control is wanted. The positive control at cooldown 0 already exists (INT-04).

**G-COOL-30.** Do not re-test t=100 / t=130 / t=165 at 60 s. The open check is the session engine’s 30 s value, through heartbeat rather than a hand-built engine:

1. Confirm the subject cooldown used to build the engine (default 30 s, or the admin value if the session actually loads it — the settings test only stores 45 and 180).
2. Fire one tier-1 decision, record the outcome as reengaged, then send DISTRACTED heartbeats at +29 s and +31 s.
3. Expected from the engine comparison `elapsed < cooldown`: no new intervention at +29 s; a new one is allowed at +31 s.
4. This was not run.

**G-COOL-EQ (P3).** The strict `<` comparison means the instant `elapsed == cooldown` is allowed to fire. The 60 s test does not sample that instant. Optional, **Not executed**.

Admin min/max are stored and a reversed pair is rejected. No recorded test shows a live session refused a cooldown below the stored minimum. That is part of G-COOL-30’s setup note, not a second copy of `test_admin_settings_lifecycle`.

## 4. Positive XP awarded once, including rollback and retry

### Already recorded

| Evidence | Assertion |
|----------|-----------|
| `test_repeated_stop_awards_xp_only_once` | Injected FOCUSED observations over a 10-minute session. First stop `xp_gained > 0`, metric `observed_v1`, focus not null. Second stop `xp_gained == 0`. Stored `StudentProgress.xp` unchanged |
| `test_claim_session_xp_award_is_atomic` | Eight concurrent claims: one True, seven False, `xp_awarded=true` |
| `test_xp_claim_and_award_rollback_then_retry` | Patched award failure leaves `xp_awarded=false` and gain 0. The retry with 120 observed focused seconds returns `xp_gained > 0` and `xp_awarded=true` |
| `test_claim_session_xp_award_commit_false_stays_uncommitted_until_outer` | `commit=False` then rollback leaves `xp_awarded=false` |
| MON-03, AN-07, `test_stop_zero_coverage_null_focus_no_focus_xp`, `test_zero_observed_focused_awards_zero_session_xp` | Zero observed focus → 0 XP. These do **not** prove the positive-once rule |

Chapter 6 should cite `test_repeated_stop_awards_xp_only_once` for “awarded once”, and the rollback test for “a failed award can be retried”. MON-03 is the zero-award stop sample only.

### Still open

No further functional test is proposed. Adding another double-stop or another patched rollback would duplicate these functions.

Limitation to keep next to the citation: the rollback failure is a patched `RuntimeError`, and the atomic test checks the claim flag rather than two HTTP stop calls. The HTTP double-stop with a positive amount is the first function in the table.

## 5. Quiz correctness and material-specific question selection

### Already recorded

| Evidence | Assertion |
|----------|-----------|
| `test_quiz_full_lifecycle_and_grading` | Electron option and short answer `  au  ` score 100; both `is_correct` true. Duplicate question ids, a second submit, and a second attempt are rejected |
| ST-04 | Attempt 201 and submit 200. No score in the sample |
| `test_manual_trigger_and_milestone_grading` | Manual tier 3; selected option 0; `is_correct is True` and the milestone row stores the answer |
| INT-02 | Response stored; `is_correct` null |
| `test_create_material_with_milestones`, TE-02 | A milestone can be saved and read back, including `correct_option` |
| `test_award_quiz_ace` | 5/5 correct awards quiz XP and the `quiz_ace` badge. It does not mark a quiz attempt |

`_pick_milestone_item` loads every active milestone on **any content in the session’s module**, ordered by `sequence_order`, and returns the first. The session helper resolves a module id and does not pass a content id. No recorded test builds two materials and checks which question appears.

### Still open

**G-QUIZ-WRONG.** One new submission on a copy of the existing chemistry fixture: choose Proton, and send a short answer other than `au`. Expected if grading matches the correct-path test: score below 100, first answer `is_correct` false, second answer `is_correct` false. **Not executed.** Do not re-submit the correct paper.

**G-MILESTONE-WHICH.** Create two materials in one module, each with a different question and a different `sequence_order`. Start a session on that module and trigger a milestone. Record which `milestone_item_id` is returned. The current picker will return the lowest `sequence_order` in the module, including an item that belongs to the material the student is not watching. That behaviour was **not executed** as a test. Until it is, the chapter should not say that questions are selected for the open material. The recorded grading test shows that the served item can be marked correct. It does not show a choice between materials.

## 6. Successful content generation and service-failure handling

### Already recorded

| Evidence | Assertion |
|----------|-----------|
| `test_llm_service_parses_json_pack` | Patched `_chat` JSON becomes a summary and one milestone |
| `test_generate_pack_endpoint_mocked` | Patched service; POST **with** a description returns 200, the fake summary, and one milestone |
| TE-03 | POST **without** `description` (`content_id`, then `module_content_id`) returns 400 “Field required”. The harness recorded the retry. Ollama was not called |
| Route `generate_material_pack` | `LLMUnavailableError` is mapped to HTTP 503. No test calls it |

The harness pass predicate accepts 200, 201, 400, 404, 500, 502, and 503. A 400 therefore satisfied TE-03 without checking generation or an outage.

### Still open

**G-LLM-503 (manual or a closed port).** Do not repeat the mocked 200 test.

1. Leave Ollama stopped, or point `LLM_BASE_URL` at a closed port.
2. As a teacher, `POST /api/courses/materials/generate-pack` with JSON `{"description": "Notes about fractions.", "title": "Fractions"}`.
3. Expected from the service and the route: HTTP 503 and an error that the LLM is unreachable or timed out. A 400 “description required” means this procedure was not followed.
4. **Not executed** on 2026-10-23.

**Successful generation.** The mocked endpoint test already asserts the success body. A live Ollama run was not archived. Optional manual add-on, still **Not executed**, and only if a model is actually running: the same POST, expect 200, a non-empty `summary`, and `milestones` whose `correct_option` values are in range. The route does not save the pack; saving is `test_create_material_with_milestones`.

**G-LLM-BADJSON (P3).** A stub that returns prose rather than JSON should surface as a failure (`LLMUnavailableError` in `_parse_pack`). **Not executed.** The valid-JSON parser test stays the success-side evidence.

## 7. Theme application and persistence

### Already recorded

| Evidence | Assertion |
|----------|-----------|
| ST-05 | Profile JSON stores `theme=sage` |
| `test_ui_preferences_patch` | PATCH response echoes `theme=calm-dark`, plus text size and reduce-motion. No follow-up GET and no pixels |
| UI-THEME-SETTINGS | Same-session screenshots: Warm is a parchment settings page with “Saved”; Calm dark is a dark settings page with “Saved”. Sage login, dashboard, settings, and course-explore screenshots were archived |
| UI-THEME-LEARNING | **Not executed** |

Profile persistence and visual application are different results. The screenshots support visual application on the settings page and the listed sage chrome. They do not support the lesson player, the quiz, or an intervention overlay.

### Still open

**G-THEME-RELOAD.** Set Calm dark, confirm “Saved”, sign out, sign in, and read `document.documentElement.getAttribute("data-theme")` plus the page background. Expected if profile load applies the token: `calm-dark` and the dark surfaces from the existing screenshot. **Not executed** as a fresh login. The screenshot sitting did not record that reload.

**G-THEME-LESSON.** Needs a subject the student can open (the theme note’s blocker).

1. Enrol the demo student on a subject that has a video and a quiz, or use the Phase 2A demo course.
2. Set Calm dark and reload.
3. Open the lesson, trigger an ambient cue (DemoPanel is enough for the overlay chrome), and open a quiz.
4. Record `data-theme` and one screenshot of each surface.
5. **Not executed.**

**G-THEME-MOTION (P3).** The preference values are already stored by `test_ui_preferences_patch`. A visual check of text size `l` and reduced motion was not archived.

## 8. Claims the existing tests already support

These are listed so they are not re-tested and then reported as new results.

| Claim | Cite |
|-------|------|
| Blank or corrupt frame → UNKNOWN, and a client FOCUSED verdict does not override it | MON-01; `test_heartbeat_with_image_returns_ml_verdict`; `test_heartbeat_unknown_via_corrupt_image` |
| UNKNOWN closes an open episode row | `test_unknown_closes_open_distraction_episode` |
| UNKNOWN does not clear pending escalation; FOCUSED does | `test_unknown_does_not_reset_pending_intervention` |
| Empty tier set fires nothing; empty subject config stays `[]` | `test_all_tiers_disabled_fires_nothing`; `test_get_enabled_tiers_preserves_empty_config` |
| A 60 s cooldown suppresses a repeat and allows one after the window | `test_cooldown_suppresses_repeat` |
| Positive `observed_v1` XP is awarded on the first stop and not on the second | `test_repeated_stop_awards_xp_only_once` |
| A failed award rolls the claim back and a retry can award XP | `test_xp_claim_and_award_rollback_then_retry` |
| A correct quiz scores 100, with case-insensitive short answers | `test_quiz_full_lifecycle_and_grading` |
| Generate-pack returns a pack when the service is patched and a description is sent | `test_generate_pack_endpoint_mocked` |
| A generate-pack body without `description` is HTTP 400 | TE-03 |
| Theme **name** is stored on the student profile | ST-05; `test_ui_preferences_patch` |
| Settings chrome was seen in Warm and Calm dark during one sitting | `dev/test_outputs/ui_theme_screenshots/04_settings_warm.png`, `06_settings_calm_dark.png` |
