# Phase 1 fix report — baseline preservation and application defects

**Date:** 2026-10-23  
**Branch:** `camtesting`  
**Remote push:** none (local commits only)  
**Scope:** Preserve evaluation baseline; fix six application/demo defects. No retraining, no feature/threshold changes, no monitoring-coverage redesign, no overwrite of historical evaluation logs or checkpoints.

Source of defects: [FINAL_SYSTEM_AUDIT.md](FINAL_SYSTEM_AUDIT.md). Checkpoint inventory: [BASELINE_CHECKPOINT_HASHES.md](BASELINE_CHECKPOINT_HASHES.md).

---

## 1. Baseline and corrected version identifiers

| Identifier | Value |
|------------|-------|
| Pre-LMS git tip (historical) | `f7bb5fa22c2fbf2ca46817db7302499eddbda0e9` (“Initial commit”) |
| **Baseline (source freeze)** | `3128555a847e62c602aaf62888cca09c78f1e33c` — *Baseline: freeze LMS and model source for evaluation* |
| **Corrected (Phase 1 fixes)** | `3e2ce9025d3ada89dc04507fbbcee5a58b91a24c` — *Fix Phase-1 application defects before evaluation* |

Baseline commit includes application source (`backend/`, `frontend/`, `models/` code and text logs), `SYSTEM.md`, and audit docs. Excluded via `.gitignore`: `*.pt` / `*.pkl` / checkpoints under `outputs/`, datasets (`data/`, `*.csv`), `backend/uploads/`, `.env*`, `node_modules/`, `thesis_handover/`, venvs.

Checkpoint SHA-256 values were recorded in `dev/BASELINE_CHECKPOINT_HASHES.md` and **re-verified unchanged** after Phase 1 (gaze / pose / engagement / fusion all `OK`). Historical reports (`models/reports/*`, `models/*_out.txt`) were not modified.

---

## 2. Files changed and reasons

| File | Reason |
|------|--------|
| `backend/app/routes/student_profile.py` | Ignore `consent_given` on student profile PATCH; guardian contact still writable; consent remains admin-only. |
| `backend/tests/test_student_profile.py` | Expect consent stays false when student sends `consent_given: true`; add dedicated regression. |
| `backend/app/services/intervention_engine.py` | Treat `enabled_tiers=None` as default `{1..4}`; treat explicit `[]` as no tiers (no coerce). |
| `backend/app/routes/session.py` | Return raw `cfg.enabled_tiers()` (may be `[]`); add `claim_session_xp_award()`; stop awards XP only after atomic claim; idempotent `end_time` UPDATE. |
| `backend/app/db_models/session.py` | Add `xp_awarded` boolean for one-time XP claim. |
| `backend/app/__init__.py` | Lightweight `ALTER TABLE sessions ADD COLUMN xp_awarded` for existing DBs. |
| `backend/tests/test_intervention_engine.py` | Regressions: empty tiers fire nothing; `_get_enabled_tiers` preserves `[]`. |
| `backend/tests/test_session.py` | Repeated stop awards XP once; concurrent claim only one winner (file-backed SQLite). |
| `backend/tests/test_phase1_script_guards.py` | Static guards: no filename probability override; fusion summary uses defined `f1_thr`. |
| `frontend/src/utils/interventionPause.js` | Shared rule: which intervention types pause video (`ambient_cue` excluded). |
| `frontend/src/components/student/VideoLearningPlayer.jsx` | Pause only when `interventionShouldPauseVideo` is true. |
| `frontend/scripts/check_intervention_pause.mjs` | Node regression for pause helper (no frontend test runner in package.json). |
| `models/test_fusion_video.py` | Remove filename-based `dist_prob` override. **Note:** filename-derived weak labels in `prep.py` are unchanged and are not independent ground truth. |
| `models/run_tests.py` | Always compute `f1_thr` so the summary line never references unbound `f12` when threshold ≈ 0.5. |

---

## 3. Reproduction evidence and regression-test results

### 3.1 Guardian consent (student profile)

- **Before:** `PATCH /api/student/profile` with `consent_given: true` wrote `GuardianConsent.consent_given`.
- **After:** field accepted for compatibility but ignored; DB remains `False`.
- **Tests:** `test_student_profile_lifecycle`, `test_student_cannot_set_guardian_consent_via_profile` — **passed**.

### 3.2 All intervention tiers disabled

- **Before:** `enabled_tiers() or [1,2,3,4]` and `enabled_tiers or [1,2,3,4]` coerced empty → all on.
- **After:** empty list preserved; engine fires nothing.
- **Tests:** `test_all_tiers_disabled_fires_nothing`, `test_get_enabled_tiers_preserves_empty_config` — **passed**.

### 3.3 Duplicate / concurrent session-stop XP

- **Before:** every `POST .../stop` called `award_session_xp` even when `end_time` already set.
- **After:** `UPDATE ... SET xp_awarded=1 WHERE xp_awarded=0`; only `rowcount==1` awards XP. Concurrent stops covered by atomic UPDATE (not a bare `if end_time is None` check).
- **Tests:** `test_repeated_stop_awards_xp_only_once`, `test_claim_session_xp_award_is_atomic` (8 threads, file SQLite) — **passed**.

### 3.4 Ambient cue pausing video

- **Before:** `VideoLearningPlayer` paused on every intervention.
- **After:** pause gated by `interventionShouldPauseVideo` (`ambient_cue` / tier-1 fallback do not pause).
- **Tests:** `node frontend/scripts/check_intervention_pause.mjs` — **passed** (no Vitest/Jest in repo).

### 3.5 Filename probability override

- **Before:** `test_fusion_video.py` capped/floored `dist_prob` from video stem.
- **After:** model probability used as-is; comment notes weak-label distinction.
- **Tests:** `test_fusion_video_has_no_filename_probability_override` — **passed**.

### 3.6 Fusion evaluation summary crash

- **Before:** `f12` only assigned inside `if abs(threshold-0.5)>0.01`, but always printed → `UnboundLocalError` when untuned (threshold 0.5).
- **After:** always compute `f1_thr`; print uses `f1_thr`.
- **Tests:** `test_run_tests_fusion_summary_defines_threshold_f1` — **passed**. Full `run_tests.py --model fusion` was **not** re-executed (would touch evaluation reporting; Phase 1 forbids overwriting historical results).

---

## 4. Full test output location

| Run | Path | Result |
|-----|------|--------|
| Full backend pytest | [dev/test_outputs/phase1_backend_pytest.txt](test_outputs/phase1_backend_pytest.txt) | **73 passed**, 488 warnings, ~99.7 s, exit 0 |
| Ambient pause helper | [dev/test_outputs/phase1_intervention_pause_check.txt](test_outputs/phase1_intervention_pause_check.txt) | All checks passed, exit 0 |

Environment: Windows, Python via `venvpy312`, pytest from that venv. Warnings are mostly `datetime.utcnow()` deprecations and SQLAlchemy legacy APIs — not failures.

Command used:

```text
cd backend
..\venvpy312\Scripts\python.exe -m pytest tests/ -q --tb=short
node frontend/scripts/check_intervention_pause.mjs
```

---

## 5. Remaining unresolved issues

These were explicitly **out of scope** for Phase 1 (see audit §5–§6). They still block a trustworthy frozen evaluation of the live ML path:

1. **Train/serve mismatch** — live heartbeat windows, Haar crops, and engagement defaults (`n < 4` with `ML_WINDOW_FRAMES=3`) still differ from training; raising the frame buffer alone does not recreate video-rate temporal features.
2. **No valid live fusion generalisation figure** — current pickle matches a leaked mixed-video window split (Acc 1.0); April `fus_out.txt` is a different package.
3. **Engagement 0.9737** recovers rule labels — not human-labelled accuracy.
4. **Shared MediaPipe VIDEO timestamps** across sessions — still present.
5. **Inference exceptions → FOCUSED** with `face_detected: true` — still present.
6. **Focus % counts unobserved time as focused** — still present.
7. **Milestone questions** not scoped to current material — still present.
8. **Filename-derived weak labels** in `model5_fusion/prep.py` — intentionally unchanged; removing the demo override does not make those labels independent ground truth.

---

*Phase 1 complete locally. Do not treat this report as evidence that model metrics were re-run or improved.*
