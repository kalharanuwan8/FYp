# Phase 2A fix report — observation validity, session isolation, coverage

**Date:** 2026-10-23 (correction pass same day)  
**Branch:** `camtesting`  
**Remote push:** none  
**Scope:** Observation validity (`UNKNOWN`), per-session MediaPipe isolation, trustworthy monitoring coverage (`observed_v1`), XP claim/reward transaction integrity. **No retraining.** No feature-definition or classification-threshold changes. Historical evaluation logs and checkpoints untouched.

Normative coverage rules: [OBSERVATION_COVERAGE_SPEC.md](OBSERVATION_COVERAGE_SPEC.md).  
Prior phase: [PHASE_1_FIX_REPORT.md](PHASE_1_FIX_REPORT.md). Audit: [FINAL_SYSTEM_AUDIT.md](FINAL_SYSTEM_AUDIT.md).

---

## 1. Version identifiers

| Identifier | Value |
|------------|-------|
| Baseline (source freeze) | `3128555a847e62c602aaf62888cca09c78f1e33c` |
| Phase 1 corrected | `3e2ce9025d3ada89dc04507fbbcee5a58b91a24c` |
| Pre–Phase-2A tip (docs) | `ae57313caed7ff109e3c284018ec4003ae1a25be` |
| **Phase 2A corrected** | *(filled after local commit — see §9)* |

This phase is **not** an improvement in model accuracy. It makes monitoring accounting and session isolation trustworthy.

---

## 2. Phase 1 XP transaction verification

### 2.1 Finding

Phase 1 `claim_session_xp_award()` performed `UPDATE … xp_awarded=1` and **`commit()`**, then `award_session_xp()` ran in a **separate** transaction. If the award path failed after a successful claim, XP was lost permanently (`xp_awarded` stayed true).

### 2.2 Fix (retained)

- `claim_session_xp_award(session_id, commit=False|True)` — optional deferred commit.
- `award_claimed_session_xp(...)` — claim + `award_session_xp(..., commit=False)` + single `commit()`; on failure **`rollback()`** so a later stop can retry.
- Session stop uses observed focused seconds for XP.
- Regression: `test_xp_claim_and_award_rollback_then_retry`.

### 2.3 `xp_awarded` migration and historical sessions

When `xp_awarded` is first added: default false, then

`UPDATE sessions SET xp_awarded = true WHERE ended_at IS NOT NULL`.

**Uncertainty documented:** prior XP grants were not stored per session. We **cannot prove** which ended sessions already received XP. Conservative seal treats **all ended sessions as already claimed** so they are not silently eligible for another award after migration.

---

## 3. MediaPipe / landmark session isolation

- Task file loaded once; **each session** creates its own `PoseLandmarker` (VIDEO mode).
- Strictly increasing timestamps are **per session**.
- Released on: explicit `POST …/stop`, and when a new session start **auto-closes** a prior open session for the same student (`clear_session` in both paths).
- **Abandoned sessions** (tab closed without stop): landmarker remains until process restart or a later start for that student auto-closes the orphaned session id.
- **Same session concurrent heartbeats** share one landmarker instance (keyed by session id); isolation is cross-session.

Covered by tests: sequential + interleaved session IDs; `test_start_clears_prior_session_landmarker`.

---

## 4. UNKNOWN observation state (correction)

| Condition | Verdict | Notes |
|-----------|---------|--------|
| Missing / undecodable / empty image | `UNKNOWN` | `reason: no_frame_data`, `confidence: null`, `face_detected: null` |
| Inference exception | `UNKNOWN` | `reason: inference_exception` |
| **Decoded image, no detected face** | **`UNKNOWN`** | **`reason: no_face`, `confidence: null`, `face_detected: false`** |
| Successful fusion / heuristic classify | `FOCUSED` / `DISTRACTED` | `inference_path` recorded separately |

**Correction vs earlier Phase 2A draft:** missing face is **not** a valid DISTRACTED observation. It must not count as focused/distracted time or escalate visual interventions.

### Intervention hold on UNKNOWN

`decide_intervention(..., observation_state=...)` must receive the state explicitly:

- `DISTRACTED` → escalate from open episode duration.
- `FOCUSED` → `reset_on_focus()` (clears pending / tier / outcome).
- `UNKNOWN` → `hold_on_unknown()`: **no** escalation, **no** focus-reset, **no** fabricated `reengaged`/`ignored`/`ended`. Pending interventions and cooldown timestamps stay unchanged until FOCUSED reset or explicit `record_outcome`.

Do **not** rely on `is_distracted=False` alone for UNKNOWN (that historically invoked focus-reset).

---

## 5. Coverage and episode rules (exact)

See [OBSERVATION_COVERAGE_SPEC.md](OBSERVATION_COVERAGE_SPEC.md).

| Constant | Value | Role |
|----------|-------|------|
| `T_support` | 3.0 s | Max forward **coverage** of one valid observation; also **episode continuity** limit |
| `T_gap_max` | 5.0 s | **Interrupted-monitoring detector only** — does not extend coverage or keep episodes continuous across unknown remainders |
| Metric version | `observed_v1` | Stored on session; not mixed with `legacy_wallclock_v0` |

**`observed_at`:** server receive/process time (UTC) when the heartbeat is handled — **not** camera capture time (client does not send capture timestamps).

Deterministic checks (tests):

1. DISTRACTED@0, DISTRACTED@4 → coverage `[0,3)` distracted, `[3,4)` unknown; episode closes at `0+T_support` and reopens at 4.
2. DISTRACTED@0, UNKNOWN@1 → support clips at t=1; episode closes at t=1.
3. No observations → coverage 0%, focus `null`.
4. Support clipped at session end.
5. `focused + distracted + unknown == session_duration` (no overlap).

Rewards: unknown time earns no focused-time XP; zero observed focused seconds → **0** XP (no minimum consolation). Atomic claim/award retained.

---

## 6. Files changed (Phase 2A + correction)

| Area | Paths |
|------|--------|
| Spec | `dev/OBSERVATION_COVERAGE_SPEC.md` |
| Coverage | `backend/app/services/observation_coverage.py`, `focus_metrics.py` |
| ML isolation + UNKNOWN / no_face | `backend/app/services/ml_service.py` |
| Session / XP / episodes | `backend/app/routes/session.py`, `gamification_service.py` |
| Intervention hold | `backend/app/services/intervention_engine.py` |
| Models / migrate | `backend/app/db_models/session.py`, `__init__.py` |
| Analytics / socket / schema | `routes/analytics.py`, `socket_events/telemetry.py`, `schemas/session_schema.py` |
| Frontend | `FocusBuddy.jsx`, `MonitoringIndicator.jsx`, `useMonitoringSession.js`, analytics/dashboard displays |
| Demo fixture | `backend/seed_phase2a_demo.py` (local `/uploads/phase2a_demo.mp4`, gitignored `*.mp4`) |
| Tests | `backend/tests/test_phase2a_observation.py`, `test_session.py`, `test_intervention_engine.py`, … |
| Docs | `SYSTEM.md`, this report |

---

## 7. Verification results

| Run | Path | Result |
|-----|------|--------|
| Targeted Phase 2A correction | [dev/test_outputs/phase2a_correction_targeted_pytest.txt](test_outputs/phase2a_correction_targeted_pytest.txt) | **44 passed** |
| Full backend pytest | [dev/test_outputs/phase2a_correction_backend_pytest.txt](test_outputs/phase2a_correction_backend_pytest.txt) | **94 passed**, ~104 s, exit 0 |
| Intervention pause helper | [dev/test_outputs/phase2a_correction_intervention_pause_check.txt](test_outputs/phase2a_correction_intervention_pause_check.txt) | All checks passed |
| Browser ambient / pause / UNKNOWN / stop | [dev/test_outputs/phase2a_correction_browser_check.txt](test_outputs/phase2a_correction_browser_check.txt) | **PASS** (mocked camera; local demo video) |

Prior Phase 2A logs (`phase2a_*_pytest.txt`) retained; correction outputs use new filenames.

### Checkpoint hash re-verify (unchanged)

Compared to [BASELINE_CHECKPOINT_HASHES.md](BASELINE_CHECKPOINT_HASHES.md):

| Asset | SHA-256 | Status |
|-------|---------|--------|
| Gaze `best.pt` | `8127a926…eba32` | OK |
| Pose `best.pt` | `a9116270…0f629` | OK |
| Engagement `model.pkl` | `d39b5f16…37e9` | OK |
| Fusion `model.pkl` | `b465e0c4…2020e6` | OK |
| MediaPipe lite `.task` | `59929e1d…d574a` | OK |

No training jobs run.

---

## 8. Remaining blockers / limitations

1. **Train/serve mismatch** (windows, crops, engagement defaults) — out of scope; still invalidates live fusion generalisation claims.
2. **No valid leave-video-out fusion figure** for the current pickle — unchanged.
3. Abandoned-tab landmarkers live until auto-close on next start or process restart (single-worker assumption).
4. Some teacher/admin UI still uses legacy colour utilities; analytics correctly return `null` focus for legacy sessions without inventing coverage.
5. Demo MP4 is local-only (`*.mp4` gitignored); re-run `seed_phase2a_demo.py` after placing `backend/uploads/phase2a_demo.mp4`.

---

## 9. Commit identifier

**Phase 2A corrected commit:** `PENDING_LOCAL_COMMIT`  
*(Updated immediately after `git commit` on `camtesting`.)*

---

*Phase 2A improves trustworthiness of monitoring accounting and session isolation. It does not claim higher model accuracy.*
