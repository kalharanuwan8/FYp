# PLAN 4 build scratchpad

## Delivered

### Phase A
- `models/scripts/annotate_clip.py` — U undo, X delete under cursor, msec seek, EOF clamp, protocol_version header, D primary / F corrections.
- Checklist: `models/scripts/annotate_all_checklist.md`
- **User action:** annotate 21 clips; approve checkpoint commit when ready.

### Phase B
- `extract.py` — `distraction_spans` policy, cover 0.6, keep `condition` column, `--baseline live|focused`, default `--labels human`.
- `windows.py` — face-only on-screen metrics, `head_roll_dev`, body-gated hand_to_face, real-timestamp dwell.
- `train.py` (v4) — FA-constrained hysteresis (≤0.5/min), `--exclude-subjects`, `--ablate`, Platt, subject weights, deterministic CPU, span detection rate, deploy to `model6_v4`, version `v4_nested_loso`.
- **Blocked on labels:** extract → train → deploy.

### Phase C
- `live.py` — calibration lock, roll baseline, rolling EMA re-baseline, clock-reset.
- `ml_service.py` — v4 pack prefer, logreg kind, face gate 0.6, body_no_face via hysteresis, absent≥10s, engagement_score, hyst gap reset, `set_session_calibrating`.
- Frontend hook — 640w JPEG 0.8, visibility/blur signals, calibrating + content_state.
- `CalibrationOverlay` wired into SubjectDetail + VideoLearningPlayer (10 s at session start).
- Schema heartbeat fields; session route overrides tab≥3s / blur≥5s.
- UNKNOWN ≤5 s keeps episode open (paused); longer UNKNOWN closes.

### Phase D
- `intervention_engine.py` — 20s timeout→ignored, id-matched outcomes, noise isolation, cooldown-at-resolution, 10s focus reset, source caps, locks.
- Frontend guards: ignore intervention while one open; null-id local break; pace only after accept; resume only if was playing; break uses `>=` elapsed.
- `self_report` column + persist; 409 on ended-session responses.
- `test_intervention_v4.py` + updated escalation/engine tests — green.

## Tests (venvpy312)
- `models/tests` + intervention suites: **green** (51 passed in last combined run; models 22 passed after trainer upgrade).

## Still open
1. User annotates 21 clips → then extract/train/deploy v4.
2. Checkpoint commit (needs user OK).
3. Phase E: `replay_live_pipeline.py`, full suite, latency, live self-test.
4. Phase F: REPORT_10 / ERRATA / SYSTEM.md timing tables.
5. Socket.IO telemetry refactor or delete (cut-order: delete OK).
6. Coverage time-anchoring via `window_end_ms` (partial).

## Annotate command
```
venvpy312\Scripts\python.exe models/scripts/annotate_clip.py --participant 1 --condition focused
```
