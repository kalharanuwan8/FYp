# Observation coverage specification (Phase 2A)

**Status:** Normative for Phase 2A implementation.  
**Scope:** Live monitored learning sessions. Does **not** change model features, thresholds, or training.  
**Metric version:** `focus_metric_version = "observed_v1"`

This document defines interval accounting before code changes. Implementation must match these rules.

---

## 1. Observation states

Each monitoring sample (heartbeat with an image, or an explicit unusable outcome) yields one of:

| State | Meaning |
|-------|---------|
| `FOCUSED` | Valid classification: learner judged focused |
| `DISTRACTED` | Valid classification: learner judged distracted |
| `UNKNOWN` | No trustworthy classification (see §2) |

`FOCUSED` and `DISTRACTED` are **valid observations**.  
`UNKNOWN` is **invalid / unusable** for focus math and visual escalation.

Inference mode (`ml_mode`: e.g. `fusion`, `heuristic`, `unavailable`) is recorded **separately** from the observation state. A successful heuristic fallback that classifies the frame remains `FOCUSED` or `DISTRACTED` with `ml_mode=heuristic` / `inference_path=heuristic`. Unusable input is `UNKNOWN` with `inference_path=unusable` and must not fabricate `face_detected: true` or a classification confidence.

---

## 2. Conditions that produce UNKNOWN

Produce `UNKNOWN` (not FOCUSED/DISTRACTED) when any of:

1. Missing or undecodable image payload (`reason: no_frame_data`).
2. Empty / zero-size / corrupt image after decode (`reason: no_frame_data`).
3. **Decoded image with no detected face** (`reason: no_face`, `face_detected: false`, `confidence: null`).
4. MediaPipe / landmark / model inference raises or returns no usable features (`reason: inference_exception`).
5. Explicit monitoring interruption flagged by the client (optional) or server-side processing abort.

Do **not** map inference exceptions or missing faces to FOCUSED or DISTRACTED.  
Do **not** fabricate `face_detected: true` or a non-null confidence for UNKNOWN.

**Preserve:** a successful heuristic/fusion classification on a usable face remains a valid `FOCUSED` / `DISTRACTED` result; that is distinct from unusable input.

---

## 3. Interval boundaries and support duration

### 3.1 Anchor timestamps

- Session wall clock: `session.start_time` … `session.end_time` (or “now” while open).
- Each observation has `observed_at`.
- Observations are ordered by `observed_at` ascending.

### 3.2 What `observed_at` represents

`observed_at` is the **server receive/process time** (UTC, stored naive-UTC) when the heartbeat or telemetry message is handled.

It is **not** the camera capture timestamp. The client does not currently send a capture-time field; do not silently label inference completion as image capture time in docs or UI copy.

### 3.3 Heartbeat interval support — two constants, two roles

| Constant | Value | Operational role |
|----------|-------|------------------|
| `T_support` | **3.0 s** | Max forward **coverage** of one valid observation. Also the **episode continuity** limit: a gap past `T_support` between valid DISTRACTED samples breaks continuous distraction for intervention duration. |
| `T_gap_max` | **5.0 s** | **Interrupted-monitoring detector** only. If the wall-clock gap between consecutive samples exceeds `T_gap_max`, the hole is classified as interrupted monitoring (more than one missed ~2 s heartbeat). It does **not** extend coverage beyond `T_support`, and it does **not** keep a distraction episode continuous across the unknown remainder. |

Rationale: browser heartbeats target ~2.0 s. `T_support` covers one late beat for accounting. `T_gap_max` flags a deeper outage for ops/analytics without bridging state. These are **accounting** constants, not ML window sizes.

**Not redundant:** coverage and episode continuity always cut at `T_support`. `T_gap_max` is a stricter hole classifier for “monitoring interrupted” reporting; unknown time already starts after `T_support` regardless.

### 3.4 How intervals are built

Walk ordered observations `o_0 … o_{n-1}` with timestamps `t_i`.

For each observation `o_i`:

1. If `o_i` is **UNKNOWN**: it contributes **no** focused or distracted coverage. It does not extend a previous state. It closes any open distraction **episode** at the UNKNOWN `observed_at` (see §5) without counting the unknown span as distracted.
2. If `o_i` is **valid** (`FOCUSED` or `DISTRACTED`):
   - The observation **covers** forward from `t_i` for up to `T_support`, but not past the next observation timestamp, and not past `session.end_time`.
   - Let `t_next = t_{i+1}` if present, else `min(t_i + T_support, session_end)`.
   - Covered length for this observation:  
     `cover_i = max(0, min(t_next, t_i + T_support, session_end) - t_i)`.
   - Attribute `cover_i` to focused or distracted according to `o_i.state`.

### 3.5 Deterministic examples

1. **DISTRACTED at t=0, DISTRACTED at t=4** (session continues):  
   Coverage: `[0,3)` distracted, `[3,4)` unknown, then from `t=4` new support.  
   Episode: close prior episode at `t=0+T_support=3`, open new at `t=4`. Intervention duration must **not** treat `[3,4)` as continuous distraction.

2. **DISTRACTED at t=0, UNKNOWN at t=1**:  
   Coverage: distracted cover stops at `t=1` (next sample clips support). Episode closes at `t=1`.

3. **No observations:** coverage 0%, `focus_percentage` null, entire `[start,end]` unknown.

4. **Support clipped at session end:** last valid at `t` with `t + T_support > end` covers only `[t, end)`.

5. **Partition:** `observed_focused + observed_distracted + unknown == session_duration` (no overlapping attributed intervals).

### 3.6 Gaps between observations

Between `t_i` and `t_{i+1}`:

- Let `gap = t_{i+1} - t_i`.
- The portion already attributed via `cover_i` (up to `T_support`) is observed.
- Any remainder `max(0, gap - T_support)` is **unknown/unobserved** time.
- If `gap > T_gap_max`, the remainder is still unknown (same formula); additionally the gap may be flagged as interrupted monitoring. Do **not** bridge with the previous verdict.

### 3.7 Session start and stop

- From `session.start_time` until the first observation: **unknown/unobserved** (no assumed focus).
- After the last observation until `session.end_time`: extend last **valid** observation by at most `T_support`; any remainder is unknown. Last **UNKNOWN** does not extend.
- If the session ends with no observations at all: entire `[start, end]` is unknown; focus percentage is **null** / unavailable.

### 3.8 Interrupted monitoring

If heartbeats stop (client backgrounded, network loss) then resume:

- The gap is unknown time under §3.6.
- Do not invent focused or distracted coverage for the gap.
- On resume, the next valid observation starts a new coverage segment.
- Open distraction episodes close on UNKNOWN, or when a later DISTRACTED arrives after a gap `> T_support` (close at prior + `T_support`, open new).

---

## 4. Aggregates to persist (per session)

| Field | Definition |
|-------|------------|
| `observed_focused_seconds` | Sum of covered lengths attributed to FOCUSED |
| `observed_distracted_seconds` | Sum of covered lengths attributed to DISTRACTED |
| `unknown_seconds` | `max(0, session_duration_seconds - observed_focused_seconds - observed_distracted_seconds)` |
| `monitoring_coverage_pct` | `100 * (observed_focused + observed_distracted) / session_duration` when duration > 0; else `0` |
| `focus_percentage` (`observed_v1`) | `100 * observed_focused / (observed_focused + observed_distracted)` when denominator > 0; else **`null`** (unavailable) |
| `focus_metric_version` | `"observed_v1"` |

Legacy wall-clock metric (session duration minus open distraction episodes, treating gaps as focused) is **`legacy_wallclock_v0`**. Do **not** mix `observed_v1` and legacy values in the same aggregate without labelling. Historical rows without coverage fields must **not** be backfilled with invented coverage; analytics that require `observed_v1` skip or separately bucket legacy sessions.

---

## 5. Episodes and interventions across unknown gaps

### 5.1 Distraction episodes

- Open episode on transition to valid `DISTRACTED`.
- Close episode on valid `FOCUSED` (re-engagement).
- On `UNKNOWN`: **close** any open distraction episode at the UNKNOWN `observed_at`. Do **not** count the unknown interval as distracted duration.
- When a later `DISTRACTED` arrives after a gap `> T_support` from the prior DISTRACTED observation: close the prior episode at `prior + T_support` and open a new episode at the new sample. Unknown gaps must not accumulate toward visual escalation timers.

### 5.2 Intervention engine

- Pass `observation_state` explicitly on each heartbeat.
- `DISTRACTED` + open episode → may escalate (duration-based tiers).
- `FOCUSED` → `reset_on_focus()` (clears pending, tier, outcome).
- `UNKNOWN` → **hold**: do not escalate, do **not** call `reset_on_focus`, do **not** fabricate `reengaged` / `ignored` / `ended`. Pending interventions and cooldown timestamps remain unchanged until a real FOCUSED reset or an explicit `record_outcome`.
- Environmental noise triggers (non-visual) remain separate and unchanged by this spec.

### 5.3 Re-engagement

Only a valid `FOCUSED` observation closes distraction as re-engagement for analytics/XP side-effects that depend on focus recovery. UNKNOWN is not re-engagement.

---

## 6. Rewards

- Focused-time XP uses **`observed_focused_seconds`** (and `observed_v1` focus fraction when needed).
- Unknown time does **not** earn focused-time XP.
- If `focus_percentage` is null (zero valid observed time), treat focus contribution as **0** for XP (no award from focus fraction); duration-based components that previously used wall-clock focused minutes must use observed focused seconds instead.
- There is **no** minimum focused-time XP consolation: zero observed focused seconds → zero focused-time XP.
- XP claim idempotency (`xp_awarded`) remains as Phase 1 (claim + award in one transaction).

---

## 7. API / UI presentation

- Return `focus_percentage` as number or `null`.
- Always return coverage fields when `focus_metric_version` is `observed_v1`.
- Frontend must not display UNKNOWN as FOCUSED; Focus Buddy treats UNKNOWN as not “on track” without alarming DISTRACTED styling (neutral / signal unclear).
- For `no_face`: show `verdict=UNKNOWN`, `reason=no_face`, `confidence=null`, `face_detected=false`.
- Do not show a fabricated confidence for other UNKNOWN reasons; omit or null confidence / face_detected when unknown due to failure.

---

## 8. Resource cleanup (landmarkers)

- Each monitored session owns its own MediaPipe VIDEO `PoseLandmarker` and timestamp counter.
- Release on explicit `POST …/stop` via `MLService.clear_session`.
- Release when a new session start auto-closes a prior open session for the same student.
- Abandoned sessions (tab closed without stop): landmarker remains until process restart or a later start for that student auto-closes the orphaned session id; document this as a known limitation for multi-worker deployments.
- Concurrent heartbeats for the **same** session_id share one landmarker instance (keyed by session id); isolation is cross-session, not intra-session parallelisation.

---

## 9. Non-goals

- No retraining; no fusion feature or threshold changes.
- No reconstruction of historical coverage from pre-Phase-2A event logs that never stored observation coverage samples.
- Not claimed as an improvement in model accuracy — only trustworthy accounting of what was observed.
