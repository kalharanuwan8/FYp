# REPORT_4 — M4 live engagement check + technical appendix (current system)

Read-only evidence against the **current** live code after the engagement fix (`ML_WINDOW_FRAMES` default **5**; real movement features when **n ≥ 2** valid landmarks). No application checkpoints or database rows were modified for the replay. Throw-away scripts: `evaluation/thesis_numbers/m4_replay.py`, `evaluation/thesis_numbers/_tmp_schema_check.py`.

Rules: every number comes from code read, a command run, or a SELECT executed. "Not determined" where evidence is missing.

**Note:** An earlier draft of this report documented Run 5 **before** the engagement fix (constant M4). This file replaces that draft and describes the system **as of this commit**.

---

## Part 1 — Does live M4 produce a constant output?

### 1. Code excerpts

#### Buffer size (`ML_WINDOW_FRAMES`)

`backend/app/services/ml_service.py` lines 104–106:

```python
        # Live heartbeats are ~0.5 Hz; keep enough frames for M4 movement features
        # (needs ≥2 valid landmarks). Default 5 ≈ 10 s live window.
        self.window_size = int(os.environ.get("ML_WINDOW_FRAMES", "5"))
```

`backend/.env` has no `ML_*` keys. Current live default is therefore **5**.

#### Live engagement feature extraction (`n < 2` fallback only)

`backend/app/services/ml_service.py` lines 487–540:

```python
    def compute_engagement_features(self, lm_buf: List[Optional[dict]]) -> dict:
        valid = [lm for lm in lm_buf if lm is not None]
        n = len(valid)
        pose_ratio = n / max(len(lm_buf), 1)
        # ...
        # Need ≥2 valid landmark frames so wrist-speed (np.diff) is defined.
        if n < 2:
            return {
                "pose_ratio": pose_ratio,
                "lw_speed_mean": 0.0, "lw_speed_std": 0.0,
                "rw_speed_mean": 0.0, "rw_speed_std": 0.0,
                "lw_to_nose_mean": 0.5, "rw_to_nose_mean": 0.5,
                "lw_to_sh_mean": 0.3, "rw_to_sh_mean": 0.3,
                "nose_jitter": 0.0,
                "lw_below_sh_ratio": 0.5, "rw_below_sh_ratio": 0.5,
            }
        # else: compute wrist speeds, distances, nose_jitter, below-shoulder ratios
```

With the live window of 5 face-present heartbeats, `n` reaches 5, so the **real feature path** runs (not the default vector).

#### Engagement probability → fusion `engagement_prob_mean`

`_score_window` (`ml_service.py` ~702–712): `eng_model.predict_proba(...)[0, 1]`.  
`build_fusion_features` (`ml_service.py` ~563): `"engagement_prob_mean": eng_prob`.

#### body_no_face never enters M4 / fusion buffer

`predict_frame_image` returns `body_no_face` **before** `buf["gaze"/"pose"/"lm"].append(...)` (`ml_service.py` ~815–860).

#### M4 `feature_cols` (checkpoint)

```text
['pose_ratio', 'lw_speed_mean', 'lw_speed_std', 'rw_speed_mean', 'rw_speed_std',
 'lw_to_nose_mean', 'rw_to_nose_mean', 'lw_to_sh_mean', 'rw_to_sh_mean',
 'nose_jitter', 'lw_below_sh_ratio', 'rw_below_sh_ratio']
```

Visibility (`*_vis`) is extracted but **not** an M4 input.

---

### 2. What exactly is defaulted?

| Question | Answer (current code) |
| --- | --- |
| Entire 12-feature vector replaced on a full live window? | **No.** Defaults apply only when **n &lt; 2**. With ≥2 valid landmarks, movement/posture features are computed from the buffer. |
| Default values (fallback only) | speeds/`nose_jitter` = 0.0; wrist–nose = 0.5; wrist–shoulder = 0.3; below-shoulder ratios = 0.5; `pose_ratio` still computed |
| Is engagement probability always the same? | **No** on live face-present windows (see Part 1.3). Fallback-only path still yields a single constant (~0.9979). |
| Are `body_no_face` frames passed to M4 / fusion buffer? | **No.** |

---

### 3. Recorded evidence

#### Session 94 storage

**Still not stored** in DB/CSV/log (same schema as before: no engagement column; Run 5 CSV has no `engagement_score` field; backend log has no `engagement` lines). Session 94 itself was recorded **before** this engagement fix, so it cannot prove current live M4 behaviour.

#### Replay on current MLService (not stored session data)

```powershell
$env:ML_FUSION_THRESHOLD="0.75"
# ML_WINDOW_FRAMES unset → live default 5
.\venvpy312\Scripts\python.exe evaluation\thesis_numbers\m4_replay.py
# Wrote evaluation\thesis_numbers\raw\m4_replay.json
```

**Fallback (n &lt; 2):** engagement_prob = **0.9978737516820408** (same constant as the old always-default path).

**Three real 5-frame MediaPipe buffers** (JPEG quality 50, 224×224; videos under `D:\uni\6th sem\IRP\Data collection\raw data\participant 1\`):

| buffer | n_valid | uses_default_vector | engagement_prob |
| --- | ---: | --- | ---: |
| natural_early (natural 0…20 step 5) | 5 | false | **0.9903172646481302** |
| focused_mid (focused 30…50 step 5) | 5 | false | **0.8865840299425033** |
| distracted_late (distracted 50…70 step 5) | 5 | false | **0.9303545394427232** |

Feature vectors are **not** the default constants (e.g. natural_early `lw_speed_mean=0.01064…`, `lw_to_nose_mean=0.940…`, `nose_jitter=0.00319…`).

| metric | value |
| --- | --- |
| Face-present buffers scored | 3 |
| Distinct engagement probs | **3** |
| Min | **0.8865840299425033** |
| Max | **0.9903172646481302** |
| Equal to fallback default? | **false** |

---

### 4. One-line conclusion

**(b) M4 output varies in the deployed configuration because wrist-speed, wrist–nose/shoulder distances, and nose_jitter are computed from the live landmark window (n ≥ 2); observed engagement probabilities on three real buffers span 0.8866–0.9903.**

---

## Part 2 — Compact technical evidence appendix

### 1. Build

```text
git rev-parse HEAD (parent before this commit work started):
b6ea923ff1819ef12212456ad5295726f3147b24

branch: expert-remediation
last commit date: 2026-10-23 08:57:42 +0530
last commit subject: Docs: record Phase 2A corrected commit hash in fix report.
uncommitted before this commit: yes (status_lines=61)
```

The commit that lands this REPORT_4 / engagement fix is recorded by `git rev-parse HEAD` after push (see end of commit section in git log).

### 2. Configuration (current live defaults)

| Setting | Value | Source |
| --- | --- | --- |
| `ML_FUSION_THRESHOLD` | **0.75** when set in process env (checkpoint pack stores 0.5) | env / `ml_service.py` |
| `ML_WINDOW_FRAMES` | **5** | default `ml_service.py:106` |
| Engagement min valid landmarks | **2** (`n < 2` → defaults) | `compute_engagement_features` |
| `ML_FACE_UPSCALE` | **1.0** | default |
| `ML_FACE_MIN_NEIGHBORS` | **5** | default |
| `ML_FACE_MIN_SIZE` | **28** | default |
| `ML_FACE_EQUALIZE` | **false** | default |
| `ML_POSE_BASELINE_FRAMES` | **8** | default |
| Cooldown | **30.0 s** | `system_settings.intervention_min_cooldown_seconds='30'` |
| Max cooldown setting | **120** | `intervention_max_cooldown_seconds` |
| Enabled tiers (DB at query time) | subject 1: tier1=False, tier2=False, tier3=True, tier4=True | `intervention_configs` SELECT |
| Heartbeat interval (self-test) | **2.0 s** | `live_webcam_selftest.py` `INTERVAL_S` |
| Database URL (password removed) | `postgresql://postgres:***@localhost:5432/FYP_LMS` | `backend/.env` |

Run 5 historically used `ML_WINDOW_FRAMES=3` and the old `n < 4` gate; that is superseded by the current defaults above.

### 3. Checkpoints

| Model | File | SHA-256 | Stored epoch |
| --- | --- | --- | --- |
| M1 | `model1_gaze/best.pt` | `8127a926c74a21b41f4398d43f8a662c653f61e31f2dd62302cd995b442eba32` | **15** |
| M2 | `model2_pose/best.pt` | `a91162707d5eff172e21f16cac93feeec9b57306dac1ca78531efd4e8050f629` | **3** |
| M4 | `model4_engagement/model.pkl` | `d39b5f16d3e78653c06fdead842518e2d6add967194474de6f632373beb237e9` | **Not determined** (no `epoch` key) |
| M5 | `model5_fusion/model.pkl` | `b465e0c48af9067b9417a696a7c510ddf34ac98779d6aea6adba94e7d42020e6` | **Not determined** (threshold 0.5 in pack) |

### 4. Tests

```powershell
cd backend
..\venvpy312\Scripts\python.exe -m pytest -q
```

```text
130 passed, 1226 warnings in 42.49s
```

(`test_s3_fusion_runtime.py` now has 7 tests, including `test_engagement_features_live_with_short_buffer`.)

| Test file | N | What these tests assert |
| --- | ---: | --- |
| `test_admin.py` | 6 | Admin list/deactivate, block self-deactivation, bulk import, settings; non-admin blocked |
| `test_analytics.py` | 1 | Analytics endpoints for authenticated user |
| `test_auth.py` | 6 | Login schema/password/success; register rejects admin/duplicate; student register |
| `test_courses.py` | 6 | Grade levels, ownership, archive, role lists, enrolment, material upload |
| `test_csv_importer.py` | 6 | CSV parse/validate, duplicates, grade-level, None/binary safety |
| `test_default_accounts.py` | 3 | Idempotent seed, default login, testing app no auto-seed |
| `test_face_gate.py` | 3 | No-face does not append buffer; upscale box mapping; min-size default |
| `test_gamification.py` | 4 | Session XP/badge, quiz ace, progress, UI preferences |
| `test_intervention_engine.py` | 12 | Tier bands, ambient/cooldown/escalation, disabled tiers, UNKNOWN holds |
| `test_intervention_escalation.py` | 7 | Tier 2 after ambient; one ambient/episode; ambient does not block Tier 2 |
| `test_milestones_and_triggers.py` | 4 | LLM pack, generate endpoint, milestones, manual trigger |
| `test_noise_monitor.py` | 14 | Baseline, streak, one-shot notice, schema, engine noise path |
| `test_phase1_script_guards.py` | 2 | No filename probability override; fusion summary threshold F1 |
| `test_phase2a_observation.py` | 20 | observed_v1 coverage, UNKNOWN, MediaPipe isolation, XP txn |
| `test_quizzes.py` | 1 | Quiz lifecycle and grading |
| `test_rbac.py` | 2 | Unauthenticated blocked; admin login |
| `test_remediation.py` | 10 | Error-rate, reason mapping, content fallbacks, API remediation |
| `test_s3_fusion_runtime.py` | 7 | Fusion threshold, body_no_face, pose baseline, **live engagement features vary** |
| `test_security_access.py` | 4 | Uploads 401; material/quiz access; hide milestone answers |
| `test_session.py` | 9 | Lifecycle, consent, heartbeat ML, noise, XP once, stop-active |
| `test_student_profile.py` | 3 | Profile lifecycle; guardian consent blocked; non-student blocked |

**Remediation:** all 10 in `test_remediation.py`.  
**Face gate / body-present:** `test_face_gate.py` (3) + `test_body_no_face_distracted_does_not_append_buffer`, `test_no_face_no_landmarks_still_unknown`, `test_landmarks_indicate_person_helper`, Phase 2A no-face tests.  
**Escalation:** all 7 in `test_intervention_escalation.py`.  
**Security:** all 4 in `test_security_access.py`.

### 5. Run 5 timestamps (historical session 94)

Recomputed from DB + CSV (unchanged facts):

| Event | UTC |
| --- | --- |
| Session 94 start | 2026-10-28 06:28:52.201702 |
| Session 94 end | 2026-10-28 06:33:51.603576 |
| read_1 start | 2026-10-28 06:29:58.139111 |
| phone start | 2026-10-28 06:31:03.393977 |
| away start | 2026-10-28 06:31:38.487106 |
| out_of_chair start | 2026-10-28 06:32:13.588551 |
| read_2 start | 2026-10-28 06:32:48.674696 |

Source files: `sessions` row id=94; `raw/live_webcam_selftest_20261028T063352Z.csv`.

### 6. Reproduction

```powershell
# Backend with frozen fusion threshold (window default 5 from code)
cd backend
$env:ML_FUSION_THRESHOLD = "0.75"
..\venvpy312\Scripts\python.exe wsgi.py

# Tests
..\venvpy312\Scripts\python.exe -m pytest -q

# Self-test (password redacted)
cd ..
$env:THESIS_API = "http://127.0.0.1:5000"
$env:THESIS_EMAIL = "student@luma.com"
$env:THESIS_PASSWORD = "***"
$env:THESIS_MODULE_ID = "2"
.\venvpy312\Scripts\python.exe evaluation\thesis_numbers\live_webcam_selftest.py

# Metrics
.\venvpy312\Scripts\python.exe evaluation\thesis_numbers\selftest_metrics.py

# M4 current-system replay
$env:ML_FUSION_THRESHOLD = "0.75"
.\venvpy312\Scripts\python.exe evaluation\thesis_numbers\m4_replay.py
```

---

## Not done / not determined

1. **Session 94 engagement time series** — never stored; and session 94 predates the engagement fix, so it is not evidence for the current live path.
2. **M4/M5 training epoch** — absent from joblib packs.
3. **Exact enabled tiers during Run 5** — current DB disables tiers 1–2 for subject 1, but Run 5 CSV shows ambient (1) and pacing_pause (2); no historical config snapshot.
4. **New live self-test after the engagement fix** — not re-run for this report; evidence is code + `m4_replay.json` + unit test `test_engagement_features_live_with_short_buffer`.
