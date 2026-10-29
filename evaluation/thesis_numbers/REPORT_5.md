# REPORT_5 — Two thesis builds: `thesis-final` and `thesis-run5-evaluated`

Local run only. No invented numbers. Branch for working tree after Part 2: `expert-remediation`.  
Python: `venvpy312\Scripts\python.exe`. Live DB: PostgreSQL `FYP_LMS` (not modified). Pytest: in-memory SQLite.

Rules followed: tags created without rewriting history; only the engagement window / fallback / one test differ between the two builds; every number below is from a command pasted above it.

---

## Part 1 — Freeze `thesis-final`

### 1.1 Working tree before commit

```text
$ git status --short
 M backend/tests/test_intervention_escalation.py
 M backend/tests/test_security_access.py
 M evaluation/thesis_numbers/REPORT_3.md
 M evaluation/thesis_numbers/REPORT_4.md
 M evaluation/thesis_numbers/_tmp_schema_check.py
 M evaluation/thesis_numbers/m4_replay.py
 M evaluation/thesis_numbers/selftest_metrics.py
?? evaluation/thesis_numbers/raw/FYP_LMS_backup_20261028_082536.dump
?? evaluation/thesis_numbers/raw/FYP_LMS_backup_20261028_113755.dump
?? evaluation/thesis_numbers/raw/FYP_LMS_backup_20261028_REPORT3.dump
?? evaluation/thesis_numbers/raw/heartbeat_cpu.db
?? evaluation/thesis_numbers/raw/heartbeat_cuda.db
```

```text
$ git branch --show-current
expert-remediation
```

```text
$ git log -3 --format="%h %s"
38be54c Add remediation, escalation, security, and live M4 engagement fix with thesis reports.
b6ea923 Docs: record Phase 2A corrected commit hash in fix report.
6b1d654 Fix Phase 2A observation validity, coverage accounting, and session isolation.
```

Note: `git diff --stat HEAD` showed content changes only in `REPORT_4.md` and `m4_replay.py` (297 insertions / 181 deletions). The other `M` paths had no content diff (line-ending noise only) and were not included in the resulting commit object beyond what `git add` could stage. Untracked dumps and heartbeat SQLite files were staged.

### 1.2 Commit and tag

```text
$ git commit -m "Thesis final build: post-evaluation engagement window change."
[expert-remediation e6c7b17] Thesis final build: post-evaluation engagement window change.
 7 files changed, 297 insertions(+), 181 deletions(-)
 create mode 100644 evaluation/thesis_numbers/raw/FYP_LMS_backup_20261028_082536.dump
 create mode 100644 evaluation/thesis_numbers/raw/FYP_LMS_backup_20261028_113755.dump
 create mode 100644 evaluation/thesis_numbers/raw/FYP_LMS_backup_20261028_REPORT3.dump
 create mode 100644 evaluation/thesis_numbers/raw/heartbeat_cpu.db
 create mode 100644 evaluation/thesis_numbers/raw/heartbeat_cuda.db
```

```text
$ git tag -a thesis-final -m "Thesis final build (5-heartbeat window, engagement fallback below 2 frames)"
```

```text
$ git rev-parse thesis-final
0fd2a925608c32c61eb44ea3cc62688c258bbfa4

$ git rev-parse "thesis-final^{commit}"
e6c7b17ec6e448594c4229c751ebc7b781f86ec3

$ git log -1 --format="%ci"
2026-10-28 19:59:50 +0530

$ git branch --show-current
expert-remediation
```

Annotated tag object `0fd2a925…` points at commit `e6c7b17…` (`Thesis final build: post-evaluation engagement window change.`).

### 1.3 `backend/.env` ML_* keys

```text
$ Get-Content backend\.env | Where-Object { $_ -match '^ML_' }
ML_* keys present: no
```

`backend/.env` contains no `ML_*` keys. Effective defaults therefore come from code.

### 1.4 Effective ML defaults in `thesis-final` (`backend/app/services/ml_service.py`)

```text
  71|        self.fusion_threshold = 0.5
```

```text
  97|        self.face_upscale = float(os.environ.get("ML_FACE_UPSCALE", "1.0"))
  98|        self.face_min_neighbors = int(os.environ.get("ML_FACE_MIN_NEIGHBORS", "5"))
  99|        self.face_min_size = int(os.environ.get("ML_FACE_MIN_SIZE", "28"))
 100|        self.face_equalize = (
 101|            os.environ.get("ML_FACE_EQUALIZE", "false").lower() == "true"
 102|        )
 103|
 104|        # Live heartbeats are ~0.5 Hz; keep enough frames for M4 movement features
 105|        # (needs ≥2 valid landmarks). Default 5 ≈ 10 s score window.
 106|        self.window_size = int(os.environ.get("ML_WINDOW_FRAMES", "5"))
 107|        # Session pose baseline: median yaw/pitch of first K face-present frames
 108|        # (laptop geometry vs BIWI); subtracted before fusion. No retrain.
 109|        self.pose_baseline_frames = int(os.environ.get("ML_POSE_BASELINE_FRAMES", "8"))
```

```text
 116|        # Env override after checkpoint default (tests stay stable when unset).
 117|        env_thr = os.environ.get("ML_FUSION_THRESHOLD", "").strip()
 118|        if env_thr:
 119|            try:
 120|                self.fusion_threshold = float(env_thr)
```

```text
 230|                    self.fusion_threshold = float(pack.get("threshold", 0.5))
```

| Setting | Effective default when env unset |
| --- | --- |
| `ML_WINDOW_FRAMES` | **5** |
| `ML_FUSION_THRESHOLD` | attribute init **0.5**; then checkpoint `pack.get("threshold", 0.5)`; process env overrides if set |
| `ML_FACE_UPSCALE` | **1.0** |
| `ML_FACE_MIN_NEIGHBORS` | **5** |
| `ML_FACE_MIN_SIZE` | **28** |
| `ML_FACE_EQUALIZE` | **false** |
| `ML_POSE_BASELINE_FRAMES` | **8** |

---

## Part 2 — Reconstruct `thesis-run5-evaluated`

### 2.1 Branch from tag

```text
$ git switch -c thesis-run5-evaluated thesis-final
Switched to a new branch 'thesis-run5-evaluated'
thesis-run5-evaluated
e6c7b17ec6e448594c4229c751ebc7b781f86ec3
```

### 2.2 Source of restored lines — **recovered**, not reconstructed

Primary source: parent side of the engagement change inside commit `38be54c` (`git diff b6ea923 38be54c -- backend/app/services/ml_service.py`). The default feature-vector numbers were an unchanged context hunk (not rewritten by the fix).

```text
$ git diff b6ea923 38be54c -- backend/app/services/ml_service.py
# (relevant hunks only)

-        # ~3s window at ~0.5 Hz heartbeat ≈ 2 frames; keep enough for short bursts
-        self.window_size = int(os.environ.get("ML_WINDOW_FRAMES", "3"))
+        # Live heartbeats are ~0.5 Hz; keep enough frames for M4 movement features
+        # (needs ≥2 valid landmarks). Default 5 ≈ 10 s score window.
+        self.window_size = int(os.environ.get("ML_WINDOW_FRAMES", "5"))

-        if n < 4:
+        # Need ≥2 valid landmark frames so wrist-speed (np.diff) is defined.
+        # Older live default of ML_WINDOW_FRAMES=3 never reached the previous
+        # n < 4 gate, so M4 always saw the constant default vector below.
+        if n < 2:
             return {
                 "pose_ratio": pose_ratio,
                 "lw_speed_mean": 0.0, "lw_speed_std": 0.0,
                 "rw_speed_mean": 0.0, "rw_speed_std": 0.0,
                 "lw_to_nose_mean": 0.5, "rw_to_nose_mean": 0.5,
                 "lw_to_sh_mean": 0.3, "rw_to_sh_mean": 0.3,
                 "nose_jitter": 0.0,
                 "lw_below_sh_ratio": 0.5, "rw_below_sh_ratio": 0.5,
             }
```

Same gate (`if n < 4:`) and the same eleven default constants also appear in the working-tree / tagged `evaluation/thesis_numbers/REPORT_4.md` Part 1 (pre-fix draft committed into `thesis-final`) and in `models/webcam_test.py`.

Files edited on this branch only:

1. `backend/app/services/ml_service.py` — window default `"3"` + comment; engagement gate `if n < 4:` (default dict unchanged).
2. `backend/tests/test_s3_fusion_runtime.py` — removed `_lm_at` and `test_engagement_features_live_with_short_buffer`.

No database, checkpoint, `SYSTEM.md`, or other application file was changed.

### 2.3 Commit and tag

```text
$ git commit -m "Reconstructed Run 5 evaluated build (3-heartbeat window, engagement fallback below 4 frames)."
[thesis-run5-evaluated a3a3c7b] Reconstructed Run 5 evaluated build (3-heartbeat window, engagement fallback below 4 frames).
 2 files changed, 3 insertions(+), 73 deletions(-)
```

```text
$ git tag -a thesis-run5-evaluated -m "Reconstructed build matching thesis self-test Run 5"
```

```text
$ git rev-parse refs/tags/thesis-run5-evaluated
47ee34d857c8bc339d0edf6d8d3e1d5ea1e73951

$ git rev-parse "refs/tags/thesis-run5-evaluated^{commit}"
a3a3c7ba9e54f92e329c7f6b2e581823111d1c3c
```

```text
$ git switch expert-remediation
Switched to branch 'expert-remediation'
expert-remediation
e6c7b17ec6e448594c4229c751ebc7b781f86ec3
```

Note: the branch name and tag name are both `thesis-run5-evaluated`, so unqualified `git rev-parse thesis-run5-evaluated` prints `warning: refname 'thesis-run5-evaluated' is ambiguous.` Prefer `refs/tags/…` / `refs/heads/…`.

---

## Part 3 — Verify the two builds

Verification used sibling worktrees so `expert-remediation` stayed checked out:

```text
$ git worktree add ..\luma-thesis-final thesis-final
Preparing worktree (detached HEAD e6c7b17)
HEAD is now at e6c7b17 Thesis final build: post-evaluation engagement window change.

$ git worktree add ..\luma-thesis-run5-evaluated refs/tags/thesis-run5-evaluated
Preparing worktree (detached HEAD a3a3c7b)
HEAD is now at a3a3c7b Reconstructed Run 5 evaluated build (3-heartbeat window, engagement fallback below 4 frames).
```

Model checkpoints are gitignored. For pytest / M4 replay each worktree received a **junction** from `models\outputs` → the main tree’s `models\outputs` (checkpoints themselves were not copied or modified). Interpreter: absolute path  
`D:\uni\6th sem\IRP\distraction model\distraction_project\venvpy312\Scripts\python.exe`.

### 3.1 Difference between the builds

```text
$ git diff --stat refs/tags/thesis-run5-evaluated refs/tags/thesis-final
 backend/app/services/ml_service.py      | 10 +++--
 backend/tests/test_s3_fusion_runtime.py | 66 +++++++++++++++++++++++++++++++++
 2 files changed, 73 insertions(+), 3 deletions(-)
```

```text
$ git diff refs/tags/thesis-run5-evaluated refs/tags/thesis-final
diff --git a/backend/app/services/ml_service.py b/backend/app/services/ml_service.py
index 87e3e7e..e68945b 100644
--- a/backend/app/services/ml_service.py
+++ b/backend/app/services/ml_service.py
@@ -101,8 +101,9 @@ class MLService:
             os.environ.get("ML_FACE_EQUALIZE", "false").lower() == "true"
         )
 
-        # ~3s window at ~0.5 Hz heartbeat ≈ 2 frames; keep enough for short bursts
-        self.window_size = int(os.environ.get("ML_WINDOW_FRAMES", "3"))
+        # Live heartbeats are ~0.5 Hz; keep enough frames for M4 movement features
+        # (needs ≥2 valid landmarks). Default 5 ≈ 10 s window window.
+        self.window_size = int(os.environ.get("ML_WINDOW_FRAMES", "5"))
         # Session pose baseline: median yaw/pitch of first K face-present frames
         # (laptop geometry vs BIWI); subtracted before fusion. No retrain.
         self.pose_baseline_frames = int(os.environ.get("ML_POSE_BASELINE_FRAMES", "8"))
@@ -491,7 +492,10 @@ class MLService:
         def col(name, axis):
             return np.array([lm[f"{name}_{axis}"] for lm in valid], dtype=float)
 
-        if n < 4:
+        # Need ≥2 valid landmark frames so wrist-speed (np.diff) is defined.
+        # Older live default of ML_WINDOW_FRAMES=3 never reached the previous
+        # n < 4 gate, so M4 always saw the constant default vector below.
+        if n < 2:
             return {
                 "pose_ratio": pose_ratio,
                 "lw_speed_mean": 0.0, "lw_speed_std": 0.0,
diff --git a/backend/tests/test_s3_fusion_runtime.py b/backend/tests/test_s3_fusion_runtime.py
index 76e6913..f9ec843 100644
--- a/backend/tests/test_s3_fusion_runtime.py
+++ b/backend/tests/test_s3_fusion_runtime.py
@@ -159,3 +159,69 @@ def test_landmarks_indicate_person_helper():
     weak = _person_landmarks()
     weak["nose_vis"] = 0.1
     assert MLService._landmarks_indicate_person(weak) is False
+
+
+def _lm_at(wrist_y: float) -> dict:
+    """Minimal pose landmarks with controllable wrist height (for engagement features)."""
+    return {
+        "nose_x": 0.5,
+        "nose_y": 0.35,
+        "nose_vis": 0.9,
+        "l_shoulder_x": 0.4,
+        "l_shoulder_y": 0.5,
+        "l_shoulder_vis": 0.9,
+        "r_shoulder_x": 0.6,
+        "r_shoulder_y": 0.5,
+        "r_shoulder_vis": 0.9,
+        "l_elbow_x": 0.35,
+        "l_elbow_y": 0.65,
+        "l_elbow_vis": 0.8,
+        "r_elbow_x": 0.65,
+        "r_elbow_y": 0.65,
+        "r_elbow_vis": 0.8,
+        "l_wrist_x": 0.3,
+        "l_wrist_y": wrist_y,
+        "l_wrist_vis": 0.8,
+        "r_wrist_x": 0.7,
+        "r_wrist_y": wrist_y,
+        "r_wrist_vis": 0.8,
+    }
+
+
+def test_engagement_features_live_with_short_buffer():
+    """With ≥2 landmarks, live buffers must not collapse to the constant default vector."""
+    MLService._instance = None
+    svc = MLService()
+    assert svc.window_size >= 2
+
+    still = [_lm_at(0.75), _lm_at(0.75), _lm_at(0.75)]
+    moving = [_lm_at(0.55), _lm_at(0.80), _lm_at(0.45)]
+
+    f_still = svc.compute_engagement_features(still)
+    f_move = svc.compute_engagement_features(moving)
+
+    # Defaults used only when n < 2; both buffers have n=3.
+    assert f_still["lw_speed_mean"] == 0.0
+    assert f_move["lw_speed_mean"] > 0.0
+    assert f_still["nose_jitter"] == 0.0 or f_still["nose_jitter"] >= 0.0
+    assert f_move != f_still
+
+    if svc.eng_model is not None and svc.eng_feature_cols:
+        import numpy as np
+
+        def _prob(feats):
+            X = np.array(
+                [[feats.get(c, 0.0) for c in svc.eng_feature_cols]],
+                dtype=np.float32,
+            )
+            return float(svc.eng_model.predict_proba(X)[0, 1])
+
+        p_still = _prob(f_still)
+        p_move = _prob(f_move)
+        assert p_still != p_move
+
+    # Single landmark still falls back to defaults.
+    one = svc.compute_engagement_features([_lm_at(0.7)])
+    assert one["lw_to_nose_mean"] == 0.5
+    assert one["lw_speed_mean"] == 0.0
+    MLService._instance = None
```

**Confirmation:** the only differences are (1) the `ML_WINDOW_FRAMES` default and its comment (`3` ↔ `5`), (2) the engagement fallback gate and its comment (`n < 4` ↔ `n < 2`; default feature values identical), and (3) the presence of `_lm_at` / `test_engagement_features_live_with_short_buffer` on `thesis-final`. Nothing else differs.

### 3.2 Tests

```text
# cwd: ..\luma-thesis-run5-evaluated\backend
$ ..\..\distraction_project\venvpy312\Scripts\python.exe -m pytest -q --tb=no
129 passed, 1312 warnings in 40.75s
```

```text
# cwd: ..\luma-thesis-final\backend
$ ..\..\distraction_project\venvpy312\Scripts\python.exe -m pytest -q --tb=no
130 passed, 1312 warnings in 43.71s
```

Actual totals: **129** (`thesis-run5-evaluated`), **130** (`thesis-final`). Matches the expected counts.

### 3.3 M4 replay

Process env for both runs: `$env:ML_FUSION_THRESHOLD = "0.75"`; `ML_WINDOW_FRAMES` removed from the process if present. The tagged `m4_replay.py` still executes `os.environ.setdefault("ML_WINDOW_FRAMES", "3")` and scores three **fixed 3-frame** buffers. Therefore the reported `window_size` in the JSON is **3 for both builds**; this exercises the engagement **gate**, not thesis-final’s code default of 5. No separate 5-frame buffer run was performed (a 5-frame buffer would never hit the Run 5 `n < 4` fallback).

#### `thesis-run5-evaluated`

```text
window_size 3
fusion_threshold 0.75
natural_early n_valid 3 buf_len 3 eng 0.9978737516820408
focused_mid n_valid 3 buf_len 3 eng 0.9978737516820408
distracted_late n_valid 3 buf_len 3 eng 0.9978737516820408
```

All three engagement probabilities are the same fallback value **0.9978737516820408** (feature vectors use the default eleven constants with `pose_ratio=1.0`).

#### `thesis-final`

```text
window_size 3
fusion_threshold 0.75
natural_early n_valid 3 buf_len 3 eng 0.9959574286305853
focused_mid n_valid 3 buf_len 3 eng 0.9947642895299946
distracted_late n_valid 3 buf_len 3 eng 0.9832519404127017
```

Three different engagement probabilities (real movement features computed because `n=3 ≥ 2`).

Replay JSON was written only inside each worktree (`…\evaluation\thesis_numbers\raw\m4_replay.json`). The main tree’s `evaluation\thesis_numbers\raw\m4_replay.json` was not overwritten by these runs.

### 3.4 Configuration check vs REPORT_3 Part 2 (Runs 4–5) + Part 3 Tier 1 rule

Checked on `refs/tags/thesis-run5-evaluated` / worktree code.

| Setting | REPORT_3 | thesis-run5-evaluated | Match? |
| --- | --- | --- | --- |
| `ML_WINDOW_FRAMES` | **3** (env unset) | default `"3"` in `ml_service.py` | Yes |
| Engagement min-obs | if **&lt;4** valid landmark frames → default feature vector | `if n < 4:` returns the same default dict (`pose_ratio` live; speeds `0.0`; nose `0.5`; shoulder `0.3`; jitter `0.0`; below-shoulder `0.5`) | Yes |
| Face upscale | **1.0** | `ML_FACE_UPSCALE` default `"1.0"` | Yes |
| Face min neighbours | **5** | `ML_FACE_MIN_NEIGHBORS` default `"5"` | Yes |
| Face min size | **28** | `ML_FACE_MIN_SIZE` default `"28"` | Yes |
| Face equalise | **false** | `ML_FACE_EQUALIZE` default `"false"` | Yes |
| Pose baseline | first **8** face-present frames; median yaw/pitch | `ML_POSE_BASELINE_FRAMES` default `"8"`; median baseline code retained | Yes |
| Fusion threshold | **0.75 from env** `ML_FUSION_THRESHOLD`; package stores **0.5** | env override path present; attribute/pack default `0.5`; Run 5 launch used `$env:ML_FUSION_THRESHOLD="0.75"` | Yes |
| `body_no_face` | no Haar face + MediaPipe person → DISTRACTED; not buffered | same early return (`reason: body_no_face`) before buffer append | Yes |
| Cooldown | **30.0 s** | `InterventionEngine(..., cooldown_seconds: float = 30.0)` / `_get_cooldown_seconds` default 30.0 | Yes |
| Tier bands | &lt;5→0; &lt;10→1; &lt;20→2; &lt;40→3; else 4 | `distraction_level_from_duration` identical thresholds | Yes |
| Tier 1 exception | ambient does **not** set pending / does **not** update `last_intervention_at` | Tier 1 branch returns after setting `_ambient_episode_key` only; no `_pending_intervention = True` and no `last_intervention_at = ts` | Yes |

Worktrees removed after capture:

```text
$ git worktree remove --force ..\luma-thesis-final
$ git worktree remove --force ..\luma-thesis-run5-evaluated
```

---

## Part 4 — Reproduction commands (thesis appendix)

Password shown as `***`. Each block shows the working directory at each step. Venv path is absolute from a sibling worktree.

Start-check (syntax / path only; live self-test and live backend against `FYP_LMS` not run):

```text
Test-Path venvpy312\Scripts\python.exe → True
py_compile backend\wsgi.py → exit 0 (both tags)
py_compile evaluation\thesis_numbers\live_webcam_selftest.py → exit 0
py_compile evaluation\thesis_numbers\selftest_metrics.py → exit 0
py_compile evaluation\thesis_numbers\m4_replay.py → exit 0
```

### 4.A — `thesis-run5-evaluated` (Run 5 configuration)

```powershell
# Repo root
Set-Location "D:\uni\6th sem\IRP\distraction model\distraction_project"
Get-Location

git worktree add ..\luma-thesis-run5-evaluated refs/tags/thesis-run5-evaluated
# If models\outputs is missing in the worktree (gitignored), junction it:
# New-Item -ItemType Junction -Path ..\luma-thesis-run5-evaluated\models\outputs `
#   -Target (Resolve-Path .\models\outputs)

$py = (Resolve-Path ".\venvpy312\Scripts\python.exe").Path

# Start backend (fusion threshold frozen as in Run 5)
Set-Location ..\luma-thesis-run5-evaluated\backend
Get-Location
$env:ML_FUSION_THRESHOLD = "0.75"
& $py .\wsgi.py

# Test suite (separate shell; cwd backend)
Set-Location "D:\uni\6th sem\IRP\distraction model\luma-thesis-run5-evaluated\backend"
Get-Location
& $py -m pytest -q

# Live webcam self-test (backend already running; password redacted)
Set-Location "D:\uni\6th sem\IRP\distraction model\luma-thesis-run5-evaluated"
Get-Location
$env:THESIS_API = "http://127.0.0.1:5000"
$env:THESIS_EMAIL = "student@luma.com"
$env:THESIS_PASSWORD = "***"
$env:THESIS_MODULE_ID = "2"
& $py .\evaluation\thesis_numbers\live_webcam_selftest.py

# Self-test metrics (reads DATABASE_URL from backend/.env when present)
Get-Location
& $py .\evaluation\thesis_numbers\selftest_metrics.py

# M4 replay (script setdefaults ML_WINDOW_FRAMES=3; leave process ML_WINDOW_FRAMES unset)
Remove-Item Env:ML_WINDOW_FRAMES -ErrorAction SilentlyContinue
$env:ML_FUSION_THRESHOLD = "0.75"
Get-Location
& $py .\evaluation\thesis_numbers\m4_replay.py
```

### 4.B — `thesis-final` (post-evaluation engagement window)

```powershell
Set-Location "D:\uni\6th sem\IRP\distraction model\distraction_project"
Get-Location

git worktree add ..\luma-thesis-final refs/tags/thesis-final
# Junction models\outputs if needed (same as 4.A)

$py = (Resolve-Path ".\venvpy312\Scripts\python.exe").Path

Set-Location ..\luma-thesis-final\backend
Get-Location
$env:ML_FUSION_THRESHOLD = "0.75"
& $py .\wsgi.py

Set-Location "D:\uni\6th sem\IRP\distraction model\luma-thesis-final\backend"
Get-Location
& $py -m pytest -q

Set-Location "D:\uni\6th sem\IRP\distraction model\luma-thesis-final"
Get-Location
$env:THESIS_API = "http://127.0.0.1:5000"
$env:THESIS_EMAIL = "student@luma.com"
$env:THESIS_PASSWORD = "***"
$env:THESIS_MODULE_ID = "2"
& $py .\evaluation\thesis_numbers\live_webcam_selftest.py

Get-Location
& $py .\evaluation\thesis_numbers\selftest_metrics.py

Remove-Item Env:ML_WINDOW_FRAMES -ErrorAction SilentlyContinue
$env:ML_FUSION_THRESHOLD = "0.75"
Get-Location
& $py .\evaluation\thesis_numbers\m4_replay.py
```

---

## Part 5 — Remote

```text
$ git remote -v
origin	https://github.com/kalharanuwan8/FYp.git (fetch)
origin	https://github.com/kalharanuwan8/FYp.git (push)
```

Exact commands from the brief (failed because the name matches both a branch and a tag):

```text
$ git push origin thesis-run5-evaluated
error: src refspec thesis-run5-evaluated matches more than one
error: failed to push some refs to 'https://github.com/kalharanuwan8/FYp.git'

$ git push origin thesis-final thesis-run5-evaluated
error: src refspec thesis-run5-evaluated matches more than one
error: failed to push some refs to 'https://github.com/kalharanuwan8/FYp.git'
```

Disambiguated push (no force):

```text
$ git push origin refs/heads/thesis-run5-evaluated
remote: Create a pull request for 'thesis-run5-evaluated' on GitHub by visiting:
remote:      https://github.com/kalharanuwan8/FYp/pull/new/thesis-run5-evaluated
To https://github.com/kalharanuwan8/FYp.git
 * [new branch]      thesis-run5-evaluated -> thesis-run5-evaluated

$ git push origin refs/tags/thesis-final refs/tags/thesis-run5-evaluated
To https://github.com/kalharanuwan8/FYp.git
 * [new tag]         thesis-final -> thesis-final
 * [new tag]         thesis-run5-evaluated -> thesis-run5-evaluated
```

`expert-remediation` itself was not pushed in this step (it remains ahead of `origin/expert-remediation` by the `thesis-final` commit locally).

---

## Not done / not verified

1. **Live webcam self-test** — not re-run for either tag (appendix commands syntax-checked only).
2. **Backend `wsgi.py` against PostgreSQL `FYP_LMS`** — not started (startup runs `db.create_all()` / default-account seed paths; database must stay untouched).
3. **`m4_replay.py` does not load thesis-final’s code default of `ML_WINDOW_FRAMES=5`** — the script `setdefault`s `"3"` and uses fixed 3-frame buffers; gate behaviour was verified; the live default of 5 for `thesis-final` was verified from source / tag diff, not from that script’s `window_size` field.
4. **Exact unqualified `git push origin thesis-run5-evaluated`** — failed due to ambiguous ref (branch + tag); succeeded only with `refs/heads/` / `refs/tags/` forms.
5. **`SYSTEM.md` on `thesis-run5-evaluated`** still documents window default 5 and “≥2 valid landmark frames” (intentionally not edited; not part of the engagement-only reversal).
6. **This file (`REPORT_5.md`)** is written after both tags existed and is **not** included in either tag.

---

## Quotable summary

The evaluated Run 5 engagement configuration was **recovered exactly** from the parent side of commit `38be54c` (`ML_WINDOW_FRAMES` default 3, `if n < 4:` fallback with the unchanged default feature constants) and frozen as annotated tag `thesis-run5-evaluated` (`a3a3c7b…`); the post-evaluation build is annotated tag `thesis-final` (`e6c7b17…`) on `expert-remediation`. Tag-to-tag diff contains only the window default, the engagement gate (and comments), and the one added test; pytest totals were **129** vs **130**; M4 replay on the script’s 3-frame buffers returned the constant **0.9978737516820408** three times on the evaluated tag and three distinct probabilities (**0.9959574286305853**, **0.9947642895299946**, **0.9832519404127017**) on the final tag; the REPORT_3 Part 2 / Tier 1 configuration table matched on every listed setting; branch and both tags were pushed to `origin` after disambiguating refs.
