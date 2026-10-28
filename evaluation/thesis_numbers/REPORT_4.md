# REPORT_4 — M4 live engagement constancy check + technical appendix

Read-only evidence for a thesis reviewer. No application code, checkpoints, configuration, or database rows were modified for this report. Throw-away scripts: `evaluation/thesis_numbers/m4_replay.py`, `evaluation/thesis_numbers/_tmp_schema_check.py`.

Rules followed: every number comes from code read, a command run, or a SELECT executed. "Not determined" is used where evidence is missing.

---

## Part 1 — Does live M4 produce a constant output?

### 1. Code excerpts

#### Buffer size (`ML_WINDOW_FRAMES`)

`backend/app/services/ml_service.py` lines 104–105:

```python
        # ~3s window at ~0.5 Hz heartbeat ≈ 2 frames; keep enough for short bursts
        self.window_size = int(os.environ.get("ML_WINDOW_FRAMES", "3"))
```

Run 5 backend launch (terminal metadata, Flask process started 2026-10-28T06:23:09.767Z):

```text
$env:ML_FUSION_THRESHOLD = "0.75"; ..\venvpy312\Scripts\python.exe wsgi.py
```

`backend/.env` contains no `ML_*` keys (checked by reading the file for lines starting `ML_`). Therefore Run 5 used the default `ML_WINDOW_FRAMES=3`.

#### Live engagement feature extraction (`n < 4` branch)

`backend/app/services/ml_service.py` lines 486–537:

```python
    def compute_engagement_features(self, lm_buf: List[Optional[dict]]) -> dict:
        valid = [lm for lm in lm_buf if lm is not None]
        n = len(valid)
        pose_ratio = n / max(len(lm_buf), 1)

        def col(name, axis):
            return np.array([lm[f"{name}_{axis}"] for lm in valid], dtype=float)

        if n < 4:
            return {
                "pose_ratio": pose_ratio,
                "lw_speed_mean": 0.0, "lw_speed_std": 0.0,
                "rw_speed_mean": 0.0, "rw_speed_std": 0.0,
                "lw_to_nose_mean": 0.5, "rw_to_nose_mean": 0.5,
                "lw_to_sh_mean": 0.3, "rw_to_sh_mean": 0.3,
                "nose_jitter": 0.0,
                "lw_below_sh_ratio": 0.5, "rw_below_sh_ratio": 0.5,
            }
        # ... full movement/posture features only when n >= 4 ...
```

With a live buffer of at most 3 frames (`window_size=3`), `n` is always ≤ 3, so the `n < 4` branch always runs.

#### Engagement probability → fusion feature `engagement_prob_mean`

`backend/app/services/ml_service.py` lines 702–712 (`_score_window`):

```python
        eng_prob = 0.5
        if self.eng_model is not None and self.eng_feature_cols:
            eng_feats = self.compute_engagement_features(lm_buf)
            eng_X = np.array(
                [[eng_feats.get(c, 0.0) for c in self.eng_feature_cols]],
                dtype=np.float32,
            )
            try:
                eng_prob = float(self.eng_model.predict_proba(eng_X)[0, 1])
            except Exception:
                eng_prob = 0.5
```

`backend/app/services/ml_service.py` lines 539–568 (`build_fusion_features`):

```python
    def build_fusion_features(
        self,
        gaze_buf: List,
        pose_buf: List,
        eng_prob: float,
    ) -> np.ndarray:
        # ... gaze/pose aggregates ...
        all_vals = {
            # ...
            "engagement_prob_mean": eng_prob,
        }
```

#### body_no_face never enters M4 / fusion buffer

`backend/app/services/ml_service.py` lines 815–835 (return before buffer append at 857–860):

```python
            face_box = self._detect_face(frame)
            if face_box is None:
                # S3: person without Haar face → DISTRACTED (body_no_face).
                # Still do not append to the fusion buffer.
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                lm_body = self.extract_landmarks(frame_rgb, sid)
                if self._landmarks_indicate_person(lm_body):
                    return (
                        "DISTRACTED",
                        0.85,
                        {
                            "reason": "body_no_face",
                            # ...
                            "inference_path": "body_no_face",
                        },
                    )
```

#### M4 `feature_cols` (from checkpoint, read-only)

```text
['pose_ratio', 'lw_speed_mean', 'lw_speed_std', 'rw_speed_mean', 'rw_speed_std',
 'lw_to_nose_mean', 'rw_to_nose_mean', 'lw_to_sh_mean', 'rw_to_sh_mean',
 'nose_jitter', 'lw_below_sh_ratio', 'rw_below_sh_ratio']
```

Visibility fields (`*_vis`) are extracted by MediaPipe but are **not** in `feature_cols`.

---

### 2. What exactly is defaulted?

| Question | Answer from code |
| --- | --- |
| Entire 12-feature vector replaced? | **No.** Eleven features are fixed defaults. `pose_ratio` is still computed as `n / len(lm_buf)`. |
| Default values (11 features) | `lw_speed_mean=0.0`, `lw_speed_std=0.0`, `rw_speed_mean=0.0`, `rw_speed_std=0.0`, `lw_to_nose_mean=0.5`, `rw_to_nose_mean=0.5`, `lw_to_sh_mean=0.3`, `rw_to_sh_mean=0.3`, `nose_jitter=0.0`, `lw_below_sh_ratio=0.5`, `rw_below_sh_ratio=0.5` |
| Can engagement probability vary? | In principle only via `pose_ratio` ∈ {0, 1/3, 1/2, 2/3, 1}. Empirically (Part 1.3 replay) **all** of those inputs yield the **same** M4 probability. |
| Are `body_no_face` frames passed to M4 / fusion buffer? | **No.** They return before `buf["gaze"/"pose"/"lm"].append(...)`. |

---

### 3. Recorded evidence from Run 5 (session 94)

#### Storage check

**Not stored** for session 94.

Command (schema SELECT via `_tmp_schema_check.py`):

```text
=== monitoring_observations + sessions columns ===
('monitoring_observations', 'id', 'integer')
('monitoring_observations', 'session_id', 'integer')
('monitoring_observations', 'observed_at', 'timestamp without time zone')
('monitoring_observations', 'state', 'character varying')
('monitoring_observations', 'confidence', 'double precision')
('monitoring_observations', 'face_detected', 'boolean')
('monitoring_observations', 'ml_mode', 'character varying')
('monitoring_observations', 'reason', 'character varying')
('monitoring_observations', 'created_at', 'timestamp without time zone')
('sessions', ... focus/coverage floats ...)
```

No engagement / JSON / diagnostics column on either table.

Run 5 CSV header (`raw/live_webcam_selftest_20261028T063352Z.csv`):

```text
timestamp_utc,phase,seconds_from_phase_start,verdict,confidence,reason,ml_mode,
intervention_fired,intervention_tier,intervention_type,http_status,error,
inference_path,gaze_label,head_pose_yaw,head_pose_pitch,head_pose_roll,
distract_prob,face_box_px,pose_baseline_yaw,pose_baseline_pitch,fusion_threshold
```

`engagement_score` is returned by the heartbeat JSON (`session.py` line 639) but **is not written** into the self-test CSV row keys (`live_webcam_selftest.py` lines 290–313).

Backend log grep for `engagement` in the Run 5 Flask terminal: **no matches**.

#### Replay (not stored session data)

Command:

```powershell
$env:ML_FUSION_THRESHOLD="0.75"
.\venvpy312\Scripts\python.exe evaluation\thesis_numbers\m4_replay.py
# Wrote evaluation\thesis_numbers\raw\m4_replay.json
```

**Exhaustive `pose_ratio` table** (default 11 features + each reachable ratio). All five rows returned the same probability:

| pose_ratio | engagement_prob |
| ---: | ---: |
| 0.0 | **0.9978737516820408** |
| 1/3 | **0.9978737516820408** |
| 0.5 | **0.9978737516820408** |
| 2/3 | **0.9978737516820408** |
| 1.0 | **0.9978737516820408** |

**Three real 3-observation MediaPipe buffers** (JPEG quality 50, 224×224; videos under `D:\uni\6th sem\IRP\Data collection\raw data\participant 1\`):

| buffer | frames | n_valid | pose_ratio | engagement_prob |
| --- | --- | ---: | ---: | ---: |
| natural_early | natural 0/10/20 | 3 | 1.0 | **0.9978737516820408** |
| focused_mid | focused 30/40/50 | 3 | 1.0 | **0.9978737516820408** |
| distracted_late | distracted 60/70/80 | 3 | 1.0 | **0.9978737516820408** |

All nine frames had landmarks present. Feature vectors were the `n < 4` default dict with `pose_ratio=1.0` (landmarks exist but movement features are not computed because `n < 4`).

Distinct engagement values observed in the replay: **1**. Min = max = `0.9978737516820408`.

---

### 4. One-line conclusion

**(a) M4 receives the full default feature vector and its output is constant in the deployed configuration**

Clarification attached to that choice (from the code + replay, not a second conclusion option): with `ML_WINDOW_FRAMES=3` the `n < 4` branch always runs; eleven features are fixed defaults; `pose_ratio` is still computed, but scoring every reachable `pose_ratio` and three real MediaPipe buffers all returned the identical probability `0.9978737516820408`. The thesis wording “entire vector defaulted” is therefore slightly stronger than the code (pose_ratio is live), but the claim that live M4 supplies a **constant** engagement probability to fusion is **confirmed**.

---

## Part 2 — Compact technical evidence appendix

### 1. Build

Commands:

```powershell
git rev-parse HEAD
git branch --show-current
git log -1 --format="%ci"
git status --short | Measure-Object -Line
```

Raw output:

```text
b6ea923ff1819ef12212456ad5295726f3147b24
expert-remediation
2026-10-23 08:57:42 +0530
status_lines=61
```

Last commit subject: `Docs: record Phase 2A corrected commit hash in fix report.`

**Uncommitted changes: yes.** `git status --short` reported 61 lines (39 modified, 22 untracked at the time of this count). Working tree includes the REPORT_3/REPORT_4 evaluation work, escalation/security fixes, and related frontend/backend edits not yet committed.

### 2. Configuration used for Run 5

| Setting | Value | Source |
| --- | --- | --- |
| `ML_FUSION_THRESHOLD` | **0.75** | Process env on Flask start (`$env:ML_FUSION_THRESHOLD="0.75"`); checkpoint package stores 0.5 |
| `ML_WINDOW_FRAMES` | **3** | Default in `ml_service.py:105` (env unset; not in `.env`) |
| `ML_FACE_UPSCALE` | **1.0** | Default `ml_service.py:97` |
| `ML_FACE_MIN_NEIGHBORS` | **5** | Default `ml_service.py:98` |
| `ML_FACE_MIN_SIZE` | **28** | Default `ml_service.py:99` |
| `ML_FACE_EQUALIZE` | **false** | Default `ml_service.py:100-102` |
| `ML_POSE_BASELINE_FRAMES` | **8** | Default `ml_service.py:108` |
| Cooldown | **30.0 s** | `system_settings.intervention_min_cooldown_seconds = '30'` (SELECT); `_get_cooldown_seconds` |
| Max cooldown (settings) | **120** | `intervention_max_cooldown_seconds='120'` (not used by engine path for min cooldown) |
| Enabled tiers (DB **now**) | subject_id=1 → tier1=**False**, tier2=**False**, tier3=**True**, tier4=**True** | `intervention_configs` SELECT via `_tmp_schema_check.py` |
| Enabled tiers (**during Run 5**) | **Not determined from a DB snapshot** — Run 5 CSV shows tier **1** (`ambient_cue`) and tier **2** (`pacing_pause`) fired six times, so those tiers were enabled at run time | CSV `live_webcam_selftest_20261028T063352Z.csv` |
| Heartbeat interval | **2.0 s** | `live_webcam_selftest.py` `INTERVAL_S = 2.0` |
| Database URL (password removed) | `postgresql://postgres:***@localhost:5432/FYP_LMS` | `backend/.env` `DATABASE_URL` |

### 3. Checkpoints

Re-hashed 2026-10-28 with `Get-FileHash -Algorithm SHA256` and epoch keys read via `torch.load` / `joblib.load`:

| Model | File | SHA-256 | Stored epoch |
| --- | --- | --- | --- |
| M1 gaze | `models/outputs/checkpoints/model1_gaze/best.pt` | `8127a926c74a21b41f4398d43f8a662c653f61e31f2dd62302cd995b442eba32` | **15** |
| M2 pose | `models/outputs/checkpoints/model2_pose/best.pt` | `a91162707d5eff172e21f16cac93feeec9b57306dac1ca78531efd4e8050f629` | **3** (`best.pt`) |
| M4 engagement | `models/outputs/checkpoints/model4_engagement/model.pkl` | `d39b5f16d3e78653c06fdead842518e2d6add967194474de6f632373beb237e9` | **Not determined** (no `epoch` key; pack has `model`, `feature_cols`, `val_best`, `metrics`) |
| M5 fusion | `models/outputs/checkpoints/model5_fusion/model.pkl` | `b465e0c48af9067b9417a696a7c510ddf34ac98779d6aea6adba94e7d42020e6` | **Not determined** (no `epoch` key; pack has `threshold=0.5`, `features`, `model`, …) |

Matches `raw/checkpoint_hashes_verified.json`.

### 4. Tests

#### Full suite

```powershell
cd backend
..\venvpy312\Scripts\python.exe -m pytest -q
```

Final totals line:

```text
129 passed, 1226 warnings in 94.21s (0:01:34)
```

Saved: `raw/pytest_report4.txt`.

#### Collect-only inventory

```powershell
..\venvpy312\Scripts\python.exe -m pytest --collect-only -q
# 129 tests collected in 1.24s
```

| Test file | N | What these tests assert (from names/docstrings/asserts read) |
| --- | ---: | --- |
| `test_admin.py` | 6 | Admin user list/deactivate, block self-deactivation, bulk import, settings CRUD; non-admin blocked |
| `test_analytics.py` | 1 | Analytics endpoints return expected payloads for an authenticated user |
| `test_auth.py` | 6 | Login schema/password/success; register rejects admin role and duplicate email; student register succeeds |
| `test_courses.py` | 6 | Grade levels, course create/ownership, archive, role-based subject lists, enrolment lifecycle, material upload |
| `test_csv_importer.py` | 6 | CSV parse/validate: valid rows, validation errors, duplicate email, grade-level checks, None/binary safety |
| `test_default_accounts.py` | 3 | Idempotent default-account seed, default student login, testing app does not auto-seed |
| `test_face_gate.py` | 3 | No-face UNKNOWN does not append to session buffer; face-box coords map under upscale; default min size matches face-gate check |
| `test_gamification.py` | 4 | Session XP + first badge, quiz-ace award, progress endpoints, UI preferences patch |
| `test_intervention_engine.py` | 12 | Duration→tier bands, ambient/cooldown/escalation/quiz hint/milestone/break, disabled-tier fallback, empty enabled_tiers, focus reset, UNKNOWN holds pending |
| `test_intervention_escalation.py` | 7 | Continuous distraction reaches Tier 2; ignore/reengage paths; one ambient per episode; disabled 1–2 fires nothing at 6 s; UNKNOWN mid-episode; ambient does not block Tier 2 |
| `test_milestones_and_triggers.py` | 4 | LLM pack parse, generate-pack endpoint, material+milestones create, manual trigger + grading |
| `test_noise_monitor.py` | 14 | Baseline median, spike/streak rules, one-shot notice, lesson/mic ignore, engine noise path vs pending/cooldown/disabled tier1, schema bounds |
| `test_phase1_script_guards.py` | 2 | Fusion video has no filename probability override; fusion summary defines threshold F1 |
| `test_phase2a_observation.py` | 20 | observed_v1 coverage accounting, UNKNOWN persistence/closing, MediaPipe isolation, XP claim/rollback, no-face UNKNOWN, episode gap continuity, pending held across UNKNOWN |
| `test_quizzes.py` | 1 | Full quiz lifecycle and grading |
| `test_rbac.py` | 2 | Unauthenticated access blocked; login works for admin fixture |
| `test_remediation.py` | 10 | Error-rate threshold, focus→reason mapping, content fallbacks A/B/C, inactive milestones, attention dual offer, failing-quiz API stores remediation |
| `test_s3_fusion_runtime.py` | 6 | Fusion threshold env override and verdict flip; body_no_face DISTRACTED without buffer append; no-face+no-landmarks UNKNOWN; pose baseline lock; landmarks person helper |
| `test_security_access.py` | 4 | Public `/uploads` 401; material file needs enrolment/ownership; student subject detail hides milestone answers; quiz read needs ownership/enrolment |
| `test_session.py` | 9 | Session lifecycle/telemetry, consent, image heartbeat ML verdict, noise notice, milestone trigger, XP once/atomic claim, list/stop-active ownership |
| `test_student_profile.py` | 3 | Profile lifecycle; student cannot set guardian consent; non-student blocked |

#### Category lists

**Remediation** (`test_remediation.py`):  
`test_error_rate_exactly_50_percent_no_trigger`, `test_decide_reason_high_focus_comprehension`, `test_decide_reason_low_focus_attention`, `test_decide_reason_no_session_or_low_coverage`, `test_content_fallback_a_document_wins`, `test_content_fallback_b_approved_pack`, `test_content_fallback_c_guided_rewatch`, `test_inactive_milestones_do_not_count_as_pack`, `test_attention_offers_guided_plus_alternative`, `test_api_failing_quiz_returns_remediation_and_stores_event`

**Face gate / body-present** (`test_face_gate.py`, `test_s3_fusion_runtime.py`, plus Phase 2A no-face):  
`test_no_face_unknown_does_not_append_to_session_buffer`, `test_detect_face_maps_box_to_original_coords_when_upscaling`, `test_detect_face_default_min_size_matches_face_gate_check`, `test_body_no_face_distracted_does_not_append_buffer`, `test_no_face_no_landmarks_still_unknown`, `test_landmarks_indicate_person_helper`, `test_predict_no_face_is_unknown_with_face_detected_false`, `test_heartbeat_no_face_persists_unknown`

**Escalation / Tier 1 exception** (`test_intervention_escalation.py`):  
`test_default_continuous_distracted_reaches_tier2`, `test_ignored_response_after_tier2_plus`, `test_reengaged_response_after_tier2_plus`, `test_only_one_ambient_cue_per_episode`, `test_enabled_tiers_3_4_at_6s_fires_nothing`, `test_unknown_mid_episode_and_focused_reset`, `test_ambient_does_not_block_tier2_inside_band`

**Security** (`test_security_access.py`):  
`test_public_uploads_blocked`, `test_material_file_requires_enrolment_or_ownership`, `test_student_subject_detail_hides_milestone_answers`, `test_quiz_read_requires_ownership_or_enrolment`

### 5. Run 5 timestamps

Recomputed from DB + CSV (no prior timeline file existed; earlier chat answer is not a repo artefact).

| Event | UTC |
| --- | --- |
| Session 94 `started_at` | 2026-10-28 06:28:52.201702 |
| Session 94 `ended_at` | 2026-10-28 06:33:51.603576 |
| Phase `read_1` start | 2026-10-28 06:29:58.139111 |
| Phase `phone` start | 2026-10-28 06:31:03.393977 |
| Phase `away` start | 2026-10-28 06:31:38.487106 |
| Phase `out_of_chair` start | 2026-10-28 06:32:13.588551 |
| Phase `read_2` start | 2026-10-28 06:32:48.674696 |

Sources: `SELECT started_at, ended_at FROM sessions WHERE id=94`; phase starts = first heartbeat timestamp minus `seconds_from_phase_start` in `raw/live_webcam_selftest_20261028T063352Z.csv`.

### 6. Reproduction

```powershell
# Backend (Run 5 frozen fusion threshold)
cd backend
$env:ML_FUSION_THRESHOLD = "0.75"
..\venvpy312\Scripts\python.exe wsgi.py

# Test suite
cd backend
..\venvpy312\Scripts\python.exe -m pytest -q

# Live webcam self-test (password redacted)
cd ..
$env:THESIS_API = "http://127.0.0.1:5000"
$env:THESIS_EMAIL = "student@luma.com"
$env:THESIS_PASSWORD = "***"   # value from local secrets / prior Run 5; not written here
$env:THESIS_MODULE_ID = "2"
.\venvpy312\Scripts\python.exe evaluation\thesis_numbers\live_webcam_selftest.py
# writes evaluation\thesis_numbers\raw\live_webcam_selftest_<UTC>.csv

# Regenerate metrics (reads DATABASE_URL from backend/.env; includes session 94 / Run 5)
.\venvpy312\Scripts\python.exe evaluation\thesis_numbers\selftest_metrics.py
# writes evaluation\thesis_numbers\raw\selftest_metrics.json

# M4 constancy replay (this report)
$env:ML_FUSION_THRESHOLD = "0.75"
.\venvpy312\Scripts\python.exe evaluation\thesis_numbers\m4_replay.py
# writes evaluation\thesis_numbers\raw\m4_replay.json
```

---

## Not done / not determined

1. **Session 94 engagement_score / engagement_prob_mean time series** — not stored in DB, CSV, or backend log; replaced by the off-line replay in `raw/m4_replay.json` (explicitly labelled replay, not session data).
2. **M4 and M5 training epoch** — no `epoch` key in the joblib packs.
3. **Exact `intervention_configs` row state at Run 5 start** — current SELECT shows tiers 1–2 disabled for subject 1, but the Run 5 CSV recorded tier 1 and tier 2 interventions; no timestamped config snapshot was kept, so the historical enabled-tier set is **Not determined** (only the CSV evidence that 1 and 2 fired).
4. **Why M4’s sklearn Pipeline ignores `pose_ratio` across {0…1}** — not inspected (tree structure / coefficients not dumped); only the observed constant `predict_proba` output is reported.
5. **No prior on-disk Run 5 timeline file** — timestamps were recomputed from CSV + DB rather than copied from a saved report file.
