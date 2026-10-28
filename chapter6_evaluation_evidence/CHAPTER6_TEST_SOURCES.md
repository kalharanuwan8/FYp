# Chapter 6 test-source references

Paths are relative to the repository root. Line numbers refer to the working tree on 2026-10-24 and locate the assertion source. Recorded outcomes are the 2026-10-23 artefacts; this file does not replace them.

Historical results to cite, without rewriting:

| Artefact | Path |
|----------|------|
| Harness Run 1 | `chapter6_evaluation_evidence/evaluation_results_run1.json` |
| Harness Run 2 | `chapter6_evaluation_evidence/evaluation_results_run2.json` |
| Harness source (thesis copy) | `chapter6_evaluation_evidence/run_system_evaluation.py` |
| Working-tree harness | `dev/test_outputs/system_evaluation/2026-10-23/run_system_evaluation.py` |
| Pytest log | `chapter6_evaluation_evidence/backend_pytest.txt` |
| Configuration | `chapter6_evaluation_evidence/evaluated_configuration.json` |
| Evaluation report | `chapter6_evaluation_evidence/SYSTEM_EVALUATION_REPORT.md` |
| Reproduction commands | `dev/test_outputs/system_evaluation/2026-10-23/REPRODUCTION.md` |
| Heartbeat timings (Run 2) | `dev/test_outputs/system_evaluation/2026-10-23/heartbeat_rtt.csv` |
| Intervention display timings | `dev/test_outputs/system_evaluation/2026-10-23/intervention_display_timing.csv` |
| Browser note | `dev/test_outputs/phase2a_correction_browser_check.txt` |
| Theme note and screenshots | `dev/UI_THEME_IMPLEMENTATION.md`; `dev/test_outputs/ui_theme_screenshots/` |

## Harness pass predicates that limit the claim

| ID | Where the predicate is written | What it accepts |
|----|--------------------------------|-----------------|
| TE-03 | `run_system_evaluation.py` generate-pack block (POST body `content_id`, then `module_content_id`; pass if status is in 200, 201, 400, 404, 500, 502, 503) | The archived body is 400 `description` required: `chapter6_evaluation_evidence/api_samples/te03_generate_pack.json` |
| MON-03 | Stop-twice block; expected text says the second stop adds no XP | `api_samples/mon03_stop.json` has `xp_gained: 0` on a session with null focus |
| INT-01 | Manual `trigger-intervention`; result note says duration and cooldown are bypassed | `api_samples/int01_manual_pending.json` |
| INT-04 | TESTING verdict injection; fixture writes `intervention_min_cooldown_seconds=0` near the top of `setup_fixtures` | `api_samples/int04_controlled_pathway.json` (`reason: test_injected`) |
| ST-04 | Attempt and submit status codes | `api_samples/st04_quiz.json` has no score |
| ST-05 | PATCH/GET theme | Value is inside `evaluation_results_run2.json`. `api_samples/st05_prefs.json` is cited and is not in this folder |

Same absence for the cited samples `mon02_ownership.json`, `int02_milestone.json`, `int03_disabled_tier.json`, `int05_unknown.json`, `te01_subject.json`, `te04_intervention_config.json`, `ad01_user.json`, `ad02_consent.json`, `ad03_student_consent.json`, `ad04_rbac.json`. Use the matching object in `evaluation_results_run2.json`.

## Requirement IDs that already exist in source

| ID | Source comment | Tests that exercise it |
|----|----------------|------------------------|
| `FR-AUTH-03` | `backend/app/db_models/user.py` (`created_by`) | `test_register_student_success` asserts `created_by` |
| `FR-AUTH-06` | `backend/app/routes/sessions.py` consent comment. That blueprint is not registered | Not applied to AD-02 or `test_monitored_session_requires_consent`. Those hit `backend/app/routes/session.py` (403 text “Parental/Guardian consent required for monitored learning sessions”), which has no requirement ID |
| `FR-TCH-03` | `backend/app/config.py` file-upload comment | `test_material_file_upload` |
| `FR-ADM-05` | `backend/app/routes/admin.py`; `frontend/src/pages/admin/SystemSettings.jsx` | `test_admin_settings_lifecycle` |
| `NFR-PRIV-02` | `backend/app/db_models/user.py` pseudonym comment | `test_register_student_success` asserts `pseudonym_id` |
| `NFR-SEC-04` | `backend/app/config.py` JWT lifetime | No test asserts the 8-hour expiry |

## Pytest functions

| Function | File | Line |
|----------|------|------|
| `test_login_schema_validation` | `backend/tests/test_auth.py` | 7 |
| `test_login_invalid_password` | `backend/tests/test_auth.py` | 13 |
| `test_login_success` | `backend/tests/test_auth.py` | 30 |
| `test_register_admin_role_rejected` | `backend/tests/test_auth.py` | 50 |
| `test_register_duplicate_email_rejected` | `backend/tests/test_auth.py` | 69 |
| `test_register_student_success` | `backend/tests/test_auth.py` | 90 |
| `test_unauthenticated_user_access` | `backend/tests/test_rbac.py` | 1 |
| `test_login` | `backend/tests/test_rbac.py` | 5 |
| `test_admin_list_users` | `backend/tests/test_admin.py` | 7 |
| `test_admin_deactivate_user` | `backend/tests/test_admin.py` | 45 |
| `test_admin_self_deactivation_blocked` | `backend/tests/test_admin.py` | 64 |
| `test_admin_bulk_import_users` | `backend/tests/test_admin.py` | 73 |
| `test_admin_settings_lifecycle` | `backend/tests/test_admin.py` | 106 |
| `test_non_admin_settings_access_blocked` | `backend/tests/test_admin.py` | 149 |
| `test_get_grade_levels` | `backend/tests/test_courses.py` | 7 |
| `test_course_creation_and_ownership` | `backend/tests/test_courses.py` | 29 |
| `test_archive_subject` | `backend/tests/test_courses.py` | 80 |
| `test_role_based_subject_list_branching` | `backend/tests/test_courses.py` | 130 |
| `test_student_enrollment_lifecycle` | `backend/tests/test_courses.py` | 178 |
| `test_material_file_upload` | `backend/tests/test_courses.py` | 234 |
| `test_parse_and_validate_csv_valid` | `backend/tests/test_csv_importer.py` | 5 |
| `test_parse_and_validate_csv_validation_errors` | `backend/tests/test_csv_importer.py` | 28 |
| `test_parse_and_validate_csv_duplicate_email_in_file` | `backend/tests/test_csv_importer.py` | 41 |
| `test_parse_and_validate_csv_grade_level_validation` | `backend/tests/test_csv_importer.py` | 58 |
| `test_parse_and_validate_csv_none_value_safety` | `backend/tests/test_csv_importer.py` | 73 |
| `test_parse_and_validate_csv_binary_file_safety` | `backend/tests/test_csv_importer.py` | 78 |
| `test_ensure_default_data_creates_accounts_and_is_idempotent` | `backend/tests/test_default_accounts.py` | 11 |
| `test_default_student_can_login` | `backend/tests/test_default_accounts.py` | 50 |
| `test_create_app_testing_does_not_auto_seed` | `backend/tests/test_default_accounts.py` | 65 |
| `test_award_session_xp_and_first_badge` | `backend/tests/test_gamification.py` | 35 |
| `test_award_quiz_ace` | `backend/tests/test_gamification.py` | 49 |
| `test_progress_endpoints` | `backend/tests/test_gamification.py` | 59 |
| `test_ui_preferences_patch` | `backend/tests/test_gamification.py` | 80 |
| `test_distraction_level_bands` | `backend/tests/test_intervention_engine.py` | 24 |
| `test_tier1_ambient_after_mild_duration` | `backend/tests/test_intervention_engine.py` | 32 |
| `test_cooldown_suppresses_repeat` | `backend/tests/test_intervention_engine.py` | 45 |
| `test_ignored_escalates_one_tier` | `backend/tests/test_intervention_engine.py` | 68 |
| `test_quiz_context_uses_hint_injection` | `backend/tests/test_intervention_engine.py` | 83 |
| `test_content_context_uses_milestone_quiz` | `backend/tests/test_intervention_engine.py` | 96 |
| `test_tier4_pacing_then_suggest_break` | `backend/tests/test_intervention_engine.py` | 107 |
| `test_disabled_tier_falls_back` | `backend/tests/test_intervention_engine.py` | 120 |
| `test_all_tiers_disabled_fires_nothing` | `backend/tests/test_intervention_engine.py` | 130 |
| `test_get_enabled_tiers_preserves_empty_config` | `backend/tests/test_intervention_engine.py` | 140 |
| `test_focus_resets_escalation` | `backend/tests/test_intervention_engine.py` | 165 |
| `test_unknown_holds_without_focus_reset` | `backend/tests/test_intervention_engine.py` | 183 |
| `test_llm_service_parses_json_pack` | `backend/tests/test_milestones_and_triggers.py` | 136 |
| `test_generate_pack_endpoint_mocked` | `backend/tests/test_milestones_and_triggers.py` | 150 |
| `test_create_material_with_milestones` | `backend/tests/test_milestones_and_triggers.py` | 177 |
| `test_manual_trigger_and_milestone_grading` | `backend/tests/test_milestones_and_triggers.py` | 209 |
| `test_baseline_is_median_of_first_five_samples` | `backend/tests/test_noise_monitor.py` | 27 |
| `test_single_spike_does_not_fire_and_quiet_sample_resets_streak` | `backend/tests/test_noise_monitor.py` | 37 |
| `test_four_sustained_loud_beats_fire` | `backend/tests/test_noise_monitor.py` | 50 |
| `test_unmarked_detection_stays_pending_so_it_is_not_lost` | `backend/tests/test_noise_monitor.py` | 59 |
| `test_notice_never_fires_again_after_being_shown` | `backend/tests/test_noise_monitor.py` | 70 |
| `test_lesson_audio_samples_are_ignored` | `backend/tests/test_noise_monitor.py` | 84 |
| `test_missing_mic_samples_are_ignored` | `backend/tests/test_noise_monitor.py` | 96 |
| `test_already_loud_room_fires_once_after_calibration` | `backend/tests/test_noise_monitor.py` | 102 |
| `test_consider_noise_fires_tier1_notice_without_touching_visual_state` | `backend/tests/test_noise_monitor.py` | 112 |
| `test_consider_noise_blocked_by_pending_and_cooldown` | `backend/tests/test_noise_monitor.py` | 125 |
| `test_ignored_noise_cue_does_not_escalate_next_visual_intervention` | `backend/tests/test_noise_monitor.py` | 136 |
| `test_consider_noise_respects_disabled_tier1` | `backend/tests/test_noise_monitor.py` | 147 |
| `test_heartbeat_schema_accepts_and_bounds_noise_fields` | `backend/tests/test_noise_monitor.py` | 152 |
| `test_intervention_response_schema_validates_noise_action` | `backend/tests/test_noise_monitor.py` | 160 |
| `test_coverage_valid_observations_and_gaps` | `backend/tests/test_phase2a_observation.py` | 41 |
| `test_coverage_zero_valid_observations_null_focus` | `backend/tests/test_phase2a_observation.py` | 69 |
| `test_coverage_unmonitored_empty_session` | `backend/tests/test_phase2a_observation.py` | 86 |
| `test_coverage_distracted_gap_unknown_remainder` | `backend/tests/test_phase2a_observation.py` | 97 |
| `test_coverage_distracted_then_unknown_clips_support` | `backend/tests/test_phase2a_observation.py` | 124 |
| `test_coverage_support_clipped_at_session_end` | `backend/tests/test_phase2a_observation.py` | 139 |
| `test_unknown_closes_open_distraction_episode` | `backend/tests/test_phase2a_observation.py` | 150 |
| `test_predict_invalid_image_is_unknown` | `backend/tests/test_phase2a_observation.py` | 192 |
| `test_predict_exception_is_unknown_not_focused` | `backend/tests/test_phase2a_observation.py` | 203 |
| `test_mediapipe_landmarkers_are_session_isolated` | `backend/tests/test_phase2a_observation.py` | 216 |
| `test_heartbeat_unknown_via_corrupt_image` | `backend/tests/test_phase2a_observation.py` | 307 |
| `test_stop_zero_coverage_null_focus_no_focus_xp` | `backend/tests/test_phase2a_observation.py` | 334 |
| `test_xp_claim_and_award_rollback_then_retry` | `backend/tests/test_phase2a_observation.py` | 356 |
| `test_claim_session_xp_award_commit_false_stays_uncommitted_until_outer` | `backend/tests/test_phase2a_observation.py` | 428 |
| `test_predict_no_face_is_unknown_with_face_detected_false` | `backend/tests/test_phase2a_observation.py` | 465 |
| `test_episode_gap_breaks_continuity_for_intervention` | `backend/tests/test_phase2a_observation.py` | 481 |
| `test_unknown_does_not_reset_pending_intervention` | `backend/tests/test_phase2a_observation.py` | 547 |
| `test_zero_observed_focused_awards_zero_session_xp` | `backend/tests/test_phase2a_observation.py` | 591 |
| `test_start_clears_prior_session_landmarker` | `backend/tests/test_phase2a_observation.py` | 627 |
| `test_heartbeat_no_face_persists_unknown` | `backend/tests/test_phase2a_observation.py` | 658 |
| `test_fusion_video_has_no_filename_probability_override` | `backend/tests/test_phase1_script_guards.py` | 11 |
| `test_run_tests_fusion_summary_defines_threshold_f1` | `backend/tests/test_phase1_script_guards.py` | 23 |
| `test_quiz_full_lifecycle_and_grading` | `backend/tests/test_quizzes.py` | 6 |
| `test_session_lifecycle_and_telemetry` | `backend/tests/test_session.py` | 75 |
| `test_monitored_session_requires_consent` | `backend/tests/test_session.py` | 143 |
| `test_heartbeat_with_image_returns_ml_verdict` | `backend/tests/test_session.py` | 197 |
| `test_sustained_background_noise_triggers_one_time_notice` | `backend/tests/test_session.py` | 232 |
| `test_trigger_milestone_quiz_intervention` | `backend/tests/test_session.py` | 326 |
| `test_repeated_stop_awards_xp_only_once` | `backend/tests/test_session.py` | 351 |
| `test_claim_session_xp_award_is_atomic` | `backend/tests/test_session.py` | 415 |
| `test_student_profile_lifecycle` | `backend/tests/test_student_profile.py` | 7 |
| `test_student_cannot_set_guardian_consent_via_profile` | `backend/tests/test_student_profile.py` | 68 |
| `test_non_student_profile_access_blocked` | `backend/tests/test_student_profile.py` | 112 |
| `test_analytics_endpoints` | `backend/tests/test_analytics.py` | 19 |

`test_default_accounts.py` is untracked and was not part of the 94 passes in `backend_pytest.txt`.

## Behaviour sources used to judge gaps

| Behaviour | Implementation | Related tests |
|-----------|----------------|---------------|
| Camera start and denial message | `frontend/src/hooks/useMonitoringSession.js` `startCamera` (about lines 134–186) | No executed denial test |
| Generate-pack validation and 503 | `backend/app/routes/courses.py` `generate_material_pack` (about lines 349–378) | TE-03; `test_generate_pack_endpoint_mocked` |
| Ollama errors | `backend/app/services/llm_service.py` `LLMUnavailableError`, `_chat`, `_parse_pack` | `test_llm_service_parses_json_pack` (patched) |
| Milestone choice | `backend/app/routes/session.py` `_pick_milestone_item` (about lines 292–308) | Grading test does not compare two materials |
| XP formula | `backend/app/services/gamification_service.py` `award_session_xp` (about lines 142–165) | Positive-once test uses `observed_focused_seconds`; `test_award_session_xp_and_first_badge` uses the legacy branch |
| Engine cooldown default 30 s | `backend/app/services/intervention_engine.py` constructor `cooldown_seconds: float = 30.0` | Suppression test passes 60.0 |
| Theme attribute | `frontend/src/context/PreferencesContext.jsx` | ST-05 and `test_ui_preferences_patch` check stored JSON; screenshots show settings chrome |

## Samples present in this folder

`api_samples/st01_login.json`, `st02_enrollments.json`, `st03_material.json`, `st04_quiz.json`, `mon01_heartbeat.json`, `mon03_stop.json`, `int01_manual_pending.json`, `int04_controlled_pathway.json`, `te02_milestones.json`, `te03_generate_pack.json`, `an06_analytics.json`.

Screenshots: `screenshots/01_student_dashboard.png`, `02_video_player.png`, `03_student_analytics.png`.
