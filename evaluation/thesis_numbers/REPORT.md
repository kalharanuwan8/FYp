# Thesis numbers

All figures below are copied from command output under `evaluation/thesis_numbers/raw/`. Deployed checkpoints were not overwritten. Retrained fusion copies are only in `evaluation/thesis_numbers/artifacts/`.

Seed for every stochastic call in `run_model_metrics.py` and `run_intervention.py`: **42**. Gaze and pose evaluation used `shuffle=False`. `torch.backends.cudnn.deterministic` was set True and `cudnn.benchmark` False. Device for M1/M2: CUDA, NVIDIA GeForce RTX 4050 Laptop GPU, torch 2.5.1+cu121.

## Commands

```text
venvpy312\Scripts\python.exe -u evaluation\thesis_numbers\run_model_metrics.py
venvpy312\Scripts\python.exe -u evaluation\thesis_numbers\run_intervention.py
venvpy312\Scripts\python.exe -u evaluation\thesis_numbers\run_heartbeat_latency.py
```

The heartbeat command was run twice. The first posting used a Haar check on the original video frame, and 29 of 50 responses came back `reason=no_face`. That file was copied to `raw/heartbeat_latency_rejected_preresize_filter.json` and is not the table in section 5. The second run filters on the decoded 224×224 JPEG with the same Haar call the server uses. Its output is `raw/heartbeat_latency.json` and is the table below.

Mtimes in section 7:

```text
venvpy312\Scripts\python.exe -c "from datetime import datetime; print(datetime.fromtimestamp(1771302232.940768).isoformat()); print(datetime.fromtimestamp(1792548257.6866052).isoformat()); print(datetime.fromtimestamp(1785058722.2753983).isoformat())"
```

## Checkpoint SHA-256

| File | SHA-256 | Bytes |
|---|---|---|
| `models/outputs/checkpoints/model1_gaze/best.pt` | `8127a926c74a21b41f4398d43f8a662c653f61e31f2dd62302cd995b442eba32` | 27089538 |
| `models/outputs/checkpoints/model1_gaze/last.pt` | `8127a926c74a21b41f4398d43f8a662c653f61e31f2dd62302cd995b442eba32` | 27089538 |
| `models/outputs/checkpoints/model1_gaze/last_epoch15_96_backup.pt` | `8127a926c74a21b41f4398d43f8a662c653f61e31f2dd62302cd995b442eba32` | 27089538 |
| `models/outputs/checkpoints/model2_pose/best.pt` | `a91162707d5eff172e21f16cac93feeec9b57306dac1ca78531efd4e8050f629` | 134253858 |
| `models/outputs/checkpoints/model2_pose/last.pt` | `61104a6df32837d4f1a0fdd8bb35d61c61a3688442e14f0f7cf46bb43a695962` | 134253858 |
| `models/outputs/checkpoints/model4_engagement/model.pkl` | `d39b5f16d3e78653c06fdead842518e2d6add967194474de6f632373beb237e9` | 2419 |
| `models/outputs/checkpoints/model5_fusion/model.pkl` | `b465e0c48af9067b9417a696a7c510ddf34ac98779d6aea6adba94e7d42020e6` | 1853 |

`best.pt`, `last.pt`, and `last_epoch15_96_backup.pt` for gaze are the same bytes. The loaded gaze file’s fields are `epoch=15`, `img_size=96`, `best_f1=0.569808`. Its key set includes `optimizer_state`, `scheduler_state`, and `scaler_state`.

## 1. M1 gaze (MobileNetV2, epoch-15 file, 96×96)

Loaded `best.pt` above. Subjects in `test.csv`: p13, p14. Subjects in `val.csv`: p11, p12. The dataset class used the packed `*_images.npy` cache next to each CSV (length-checked against the CSV). Label order for the confusion matrices is center, left, right, down.

### Test (n = 5996)

| Metric | Value |
|---|---|
| Accuracy | 0.6017344896597732 |
| Macro-F1 | 0.5593556663019074 |

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| center | 0.590815627141878 | 0.7305084745762712 | 0.6532777567260326 | 2360 |
| left | 0.8013318534961155 | 0.5224312590448625 | 0.6325010950503723 | 1382 |
| right | 0.23903966597077245 | 0.7508196721311475 | 0.36262866191607285 | 305 |
| down | 0.7653814602132896 | 0.4787070292457671 | 0.5890151515151515 | 1949 |

Confusion matrix, rows true, columns predicted (center, left, right, down):

|  | center | left | right | down |
|---|---|---|---|---|
| center | 1724 | 90 | 443 | 103 |
| left | 478 | 722 | 10 | 172 |
| right | 60 | 5 | 229 | 11 |
| down | 656 | 84 | 276 | 933 |

### Validation (n = 9182)

| Metric | Value |
|---|---|
| Accuracy | 0.6098889130908299 |
| Macro-F1 | 0.5422462958962487 |

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| center | 0.7155571377714489 | 0.5113202747392521 | 0.5964391691394659 | 3931 |
| left | 0.46963123644251625 | 0.43213572854291415 | 0.4501039501039501 | 1002 |
| right | 0.32345876701361087 | 0.5603328710124826 | 0.4101522842639594 | 721 |
| down | 0.6551642075202284 | 0.780328798185941 | 0.7122897800776197 | 3528 |

|  | center | left | right | down |
|---|---|---|---|---|
| center | 2010 | 334 | 615 | 972 |
| left | 226 | 433 | 1 | 342 |
| right | 179 | 3 | 404 | 135 |
| down | 394 | 152 | 229 | 2753 |

### How the checkpoint was selected

`models/src/model1_gaze/train.py` saves `best.pt` only when validation macro-F1 strictly improves (`is_best = val_f1 > best_f1`, lines 292–317). `models/outputs/logs/model1_gaze/train_log.csv` has 15 rows. The maximum `val_f1` in that file is **0.569808 at epoch 2** (also `val_acc` 0.622305). Epoch 15 in the same file is `train_loss` 0.143933, `val_acc` 0.609998, `val_f1` 0.542339.

The file now at `best.pt` reports `epoch` 15 and `best_f1` 0.569808, and it is byte-identical to `last.pt`. In the current training script, `last.pt` stores the running `best_f1` together with optimizer state, while the `is_best` save of `best.pt` does not store optimizer state. The loaded file has optimizer state. So the deployed bytes are the epoch-15 `last.pt` snapshot. The log’s best validation macro-F1 is epoch 2, and the `best_f1` field stored inside the epoch-15 file is that earlier peak (0.569808), which matches epoch 2’s `val_f1` and does not match epoch 15’s logged `val_f1` of 0.542339.

The validation metrics recomputed in this run (accuracy 0.6098889130908299, macro-F1 0.5422462958962487) are a fresh forward pass. They are close to the epoch-15 log row and are not the same numbers as that row.

## 2. M2 head pose (ResNet-18)

Loaded `models/outputs/checkpoints/model2_pose/best.pt`. Stored fields: `epoch` **3**, `best_val` **6.01516703932612**. Test subjects 18, 19, 20 (n scored = 1672, missing images = 0). Validation subjects 15, 16, 17 (n scored = 1963, missing images = 0). MAE is the mean of `|prediction − target|` in degrees. The mean column is the unweighted mean of the three MAEs.

| Split | n | Yaw MAE | Pitch MAE | Roll MAE | Mean of the three |
|---|---|---|---|---|---|
| Test 18–20 | 1672 | 6.8511649737292775 | 5.21211219376829 | 5.720455477493994 | 5.927910881663853 |
| Val 15–17 | 1963 | 6.657398624665103 | 7.210128475504096 | 5.596910650234186 | 6.488145916801128 |

`models/src/model2_pose/train.py` lines 207–211 save `best.pt` when validation SmoothL1 loss is lower than `best_val`, and the checkpoint stores the loop variable `epoch` plus that `best_val`. No per-epoch pose validation log was found under `models/outputs` (the search list in `raw/m2_pose.json` is empty). The stored `best_val` is 6.01516703932612. A line that says this was the lowest of 10 epochs is not in a log file on disk. See Could not run.

The current training loop is `for epoch in range(start_epoch, args.epochs)` starting at 0, and it prints `Epoch {epoch+1}` while saving the 0-based index. Under that code, a stored `epoch` of 3 is the loop index whose printed label would be epoch 4. The file itself only contains the integer 3. There is no log to show which convention wrote it.

## 3. M4 engagement

Deployed `model.pkl` was not refit. The 25% hold-out was recreated with `train_test_split(test_size=0.25, random_state=42, stratify=y)` on `labeled.csv` after dropping rows with missing `active_work` (302 rows). Test n = **76** (34 inactive, 42 active_work).

These labels come from the heuristic rules in `models/src/model4_engagement/labelweak.py`. The scores are agreement with those rules.

Positive class for precision, recall, and F1 is `active_work = 1`.

| Metric | Value |
|---|---|
| Accuracy | 0.9736842105263158 |
| Precision (class 1) | 0.9545454545454546 |
| Recall (class 1) | 1.0 |
| F1 (class 1) | 0.9767441860465116 |
| Macro-F1 | 0.9732205778717407 |

Confusion matrix, rows true, columns predicted, labels `[0, 1]`:

|  | pred 0 | pred 1 |
|---|---|---|
| true 0 | 32 | 2 |
| true 1 | 0 | 42 |

## 4. M5 late fusion

Deployed pickle: 9 features in this order: `p_center_mean`, `p_left_mean`, `p_right_mean`, `p_down_mean`, `gaze_away_ratio`, `yaw_mean`, `pitch_mean`, `roll_mean`, `engagement_prob_mean`. Threshold 0.5. `threshold_tuning.enabled` is false. `class_weight` is null. `C` is 1.0. `max_iter` is 2000.

Positive class is `y = 1` (distracted). Precision, recall, and F1 below are for that class. ROC-AUC uses `predict_proba` for class 1, except the rule baseline, which uses the 0/1 rule output as the score.

### 4a. Existing stratified test file

`models/data/processed/model5_fusion/test.csv`, n = 120 (forced 52, distracted 45, natural 23).

| Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

Confusion matrix labels `[0, 1]`: `[[75, 0], [0, 45]]`.

### 4b. Blocked temporal split

Source rows are the concatenation of the existing train, val, and test CSVs (ambiguous windows were already removed when those files were built). Within each `video_id`, rows are sorted by `window_start_sec`. Cuts are `c1 = floor(0.70 n)` and `c2 = floor(0.85 n)`. Train is `[0, c1−1)`, val is `[c1+1, c2−1)`, test is `[c2+1, n)`. That drops the two indices on the train|val cut (`c1−1`, `c1`) and the two on the val|test cut (`c2−1`, `c2`).

| Video | n | train | val | test | dropped `window_start_sec` |
|---|---|---|---|---|---|
| distracted | 302 | 210 | 43 | 45 | 210, 211, 255, 256 |
| forced | 317 | 220 | 46 | 47 | 220, 221, 268, 269 |
| natural | 181 | 125 | 25 | 27 | 125, 126, 152, 153 |

Pooled test n = **119**. A new `StandardScaler + LogisticRegression(C=1.0, solver=lbfgs, max_iter=2000, random_state=42)` was fit on the blocked train rows only. The deployed `model.pkl` was not replaced. The copy is `evaluation/thesis_numbers/artifacts/m5_blocked_all9.joblib`. Decision threshold 0.5.

| Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

Confusion matrix: `[[74, 0], [0, 45]]`.

### 4c. Rule baseline

Rule applied to the feature columns: distracted if `gaze_away_ratio > 0.20` or `|yaw_mean| > 10` or `|pitch_mean| > 10`.

Existing test (n = 120):

| Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| 0.375 | 0.375 | 1.0 | 0.5454545454545454 | 0.5 |

Confusion matrix: `[[0, 75], [0, 45]]`. Every test window was scored distracted by the rule. ROC-AUC is 0.5 because the score is constant.

Blocked test (n = 119):

| Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| 0.37815126050420167 | 0.37815126050420167 | 1.0 | 0.5487804878048781 | 0.5 |

Confusion matrix: `[[0, 74], [0, 45]]`.

### 4d. Ablation on the blocked test (n = 119)

Each row is a newly fit copy of the same pipeline on the blocked train split, evaluated on the blocked test split, threshold 0.5.

| Features | Accuracy | Precision | Recall | F1 | ROC-AUC | Confusion |
|---|---|---|---|---|---|---|
| 1–5 gaze | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | `[[74, 0], [0, 45]]` |
| 1–8 gaze + head | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | `[[74, 0], [0, 45]]` |
| all 9 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | `[[74, 0], [0, 45]]` |

## 5. Full-path heartbeat latency (face present)

HTTP POST to `http://127.0.0.1:<port>/api/session/<id>/heartbeat` on a throwaway sqlite database. Frames are from `D:\uni\6th sem\IRP\Data collection\raw data\participant 1\` (`natural.mp4`, then `focused.mp4`, then `distracted.mp4`). Each frame is resized with `cv2.resize` to 224×224 (`INTER_LINEAR`) and encoded with OpenCV JPEG quality 50, which is the numeric counterpart of `canvas.toDataURL('image/jpeg', 0.5)` in `useMonitoringSession.js`. The encoder is OpenCV. A frame is kept only if Haar `detectMultiScale(gray, 1.1, 5, minSize=(50, 50))` finds a face on the decoded JPEG, the same call as `ml_service.py`.

One heartbeat is the warm-up and is excluded from n, min, median, p95, and max. The next 50 are the timed set. p95 is NumPy `percentile(..., 95, method="linear")`, checked against the explicit index `(n-1)*0.95` interpolation. Session start is timed separately because `start_session` constructs `MLService` and that is when the checkpoints load.

`ml_mode` was `full` on the warm-up and on all 50 timed responses. `face_detected` was true on all 50. `reason=no_face` count was 0. All 50 HTTP statuses were 200.

### CUDA available

Server line: `THESIS_SERVER_CUDA available=True device_count=1 name=NVIDIA GeForce RTX 4050 Laptop GPU`.

| | milliseconds |
|---|---|
| Session start (checkpoint load) | 5982.502599945292 |
| Warm-up heartbeat | 7409.850399941206 |
| n | 50 |
| min | 64.12989995442331 |
| median | 91.80050005670637 |
| p95 linear | 118.21864998200907 |
| max | 126.24519993551075 |

Warm-up verdict FOCUSED, `face_detected` true. Timed verdicts: FOCUSED 48, DISTRACTED 2.

### CUDA disabled

`CUDA_VISIBLE_DEVICES=-1` in the server process. Server line: `THESIS_SERVER_CUDA available=False device_count=0 name=none`.

| | milliseconds |
|---|---|
| Session start (checkpoint load) | 5475.584300002083 |
| Warm-up heartbeat | 546.2958000134677 |
| n | 50 |
| min | 70.01210004091263 |
| median | 97.23230008967221 |
| p95 linear | 147.6657049031928 |
| max | 207.08590000867844 |

Warm-up verdict FOCUSED, `face_detected` true. Timed verdicts: FOCUSED 48, DISTRACTED 2.

Times are localhost HTTP round trips (JSON body, route, inference, database write). They are not browser-to-server times from another machine.

## 6. Haar face detection vs head yaw (BIWI test)

Same call as `MLService.detect_face_crop` / `detect_eye_crop`: `detectMultiScale(gray, 1.1, 5, minSize=(50, 50))` with `haarcascade_frontalface_default.xml`. Frames are the images listed in `models/data/processed/model2_pose/test.csv` (subjects 18, 19, 20; 1672 rows; 0 unreadable). Those exports are 224×224. Bins are lower-inclusive and upper-exclusive. `>60` is `|yaw| >= 60`.

| \|yaw\| bin | Readable frames | Face found | Ratio |
|---|---|---|---|
| 0–15° | 1314 | 16 | 0.0121765601217656 |
| 15–30° | 253 | 0 | 0.0 |
| 30–45° | 94 | 0 | 0.0 |
| 45–60° | 9 | 0 | 0.0 |
| >60° | 2 | 0 | 0.0 |

A spot check of `images/18/frame_00000.png` (224×224) returned 0 faces at `minSize=(50, 50)` and 1 face of 28×28 pixels when the minimum size was lowered. The deployed minimum size is 50×50, so that frame counts as not found.

## 7. Natural-recording false-alarm check

Joined stored window files for `video_id=natural` the same way as `models/src/model5_fusion/prep.py`. n = **181**.

This is the stored window table, not a new forward pass of the epoch-15 gaze file. Local mtimes from the command above:

| File | Local time |
|---|---|
| `window_preds_natural.csv` | 2026-02-17T09:53:52.940768 |
| gaze `best.pt` | 2026-10-21T07:34:17.686605 |
| fusion `model.pkl` | 2026-07-26T15:08:42.275398 |

M1 argmax from the stored probabilities (`p_center`, `p_left`, `p_right`, `p_down`), which matches the stored `pred_name` column on all 181 rows:

| Class | Windows |
|---|---|
| center | 0 |
| left | 0 |
| right | 181 |
| down | 0 |

Mean `p_center` = **0.258517665016717**.

Deployed M5 (threshold 0.5) on these 181 windows: **0** classified DISTRACTED. Ratio = **0.0**.

Labels in the fusion set come from the weak rules, and natural windows that pass the geometric check are labelled focused. The 0.0 figure is the deployed classifier’s output on these feature rows.

## 8. Live webcam script

Written, not executed. Path:

`evaluation/thesis_numbers/live_webcam_selftest.py`

```text
venvpy312\Scripts\python.exe evaluation\thesis_numbers\live_webcam_selftest.py
```

It expects the real backend at `http://127.0.0.1:5000` (override `THESIS_API`, `THESIS_EMAIL`, `THESIS_PASSWORD`, `THESIS_MODULE_ID`). On-screen prompts run: 60 s reading text including the screen edges, 30 s looking down at a phone, 30 s head fully away, 30 s out of the chair, 60 s reading again. A 5 s gap between phases sends no heartbeat. Every heartbeat is logged (timestamp, verdict, confidence, reason, ml_mode, intervention fired, tier). When the window is closed it writes a CSV under `evaluation/thesis_numbers/raw/` and prints a per-phase table: fraction FOCUSED / DISTRACTED / UNKNOWN, seconds from phase start to the first DISTRACTED verdict, and seconds to the first intervention with tier. The label printed with that table is **developer self-test, single adult participant**.

There is no results table from this protocol in this run.

## 9. Intervention engine, default settings

`InterventionEngine(cooldown_seconds=30.0, enabled_tiers=None)`, which sets tiers `{1, 2, 3, 4}`. Continuous `DISTRACTED` heartbeats at t = 0, 2, …, 120 (61 heartbeats). Episode duration uses the same formula as `DistractionEvent.duration_seconds`. The production path does not pass `now`, so it uses `time.time()`. The main simulations use `now = 1700000000 + t` so that a stored `last_intervention_at` of 0 does not fall inside a 30 s cooldown. A separate run uses a clock that starts at 0.

### (a) No learner response

| Second | Tier | Type |
|---|---|---|
| 6 | 1 | ambient_cue |

No other intervention fired. `_pending_intervention` was still true at t = 120.

### (b) `record_outcome("acknowledged")` 2 s after each prompt

| Second | Tier | Type |
|---|---|---|
| 6 | 1 | ambient_cue |

`record_outcome` returns immediately unless the string is `reengaged`, `ignored`, or `ended` (`intervention_engine.py` lines 85–88). `"acknowledged"` does not clear the pending lock. The trace shows pending still true after that call.

Two extra calls of the same simulator, same clock, are in `raw/intervention.json` because they show whether tier 2 appears when the outcome is one the engine accepts.

`ignored` at t = prompt+2:

| Second | Tier | Type |
|---|---|---|
| 6 | 1 | ambient_cue |
| 36 | 3 | milestone_quiz |
| 66 | 4 | content_pacing_reduction |
| 96 | 4 | suggest_break |

`reengaged` at t = prompt+2 produced the same four rows in this 120 s run. Tier 2 does not appear in any of these runs.

### `enabled_tiers=[3, 4]`, episode duration 6 s

`duration_seconds` was 6.0. `fired` was null. `pending_after` was false. Level at 6 s is 1 (`distraction_level_from_duration`: under 5 s is 0, 5 s up to 10 s is 1). `_resolve_enabled_tier` starts at the requested tier and only decrements (`intervention_engine.py` lines 254–261). Tier 1 is not enabled, so the function returns `None`. It does not select tier 3 or 4.

### What clears the pending lock after a tier-1 ambient cue

There is no automatic timeout and no tier-1 special case. The lock is set true for every fired intervention, including ambient (`intervention_engine.py` lines 182–185).

It is cleared in `record_outcome` when the string is one of `reengaged`, `ignored`, `ended`:

```85:93:backend/app/services/intervention_engine.py
    def record_outcome(self, outcome: str):
        outcome = (outcome or "").lower().strip()
        if outcome not in {"reengaged", "ignored", "ended"}:
            return
        self.last_outcome = outcome
        self._pending_intervention = False
        if outcome == "reengaged":
            self.last_tier = None
            self.last_outcome = "reengaged"
```

It is also cleared when the observation is not `DISTRACTED` and not `UNKNOWN`, via `reset_on_focus`:

```95:99:backend/app/services/intervention_engine.py
    def reset_on_focus(self):
        """Full de-escalate when verdict flips to focused (confirmed re-engagement)."""
        self.last_tier = None
        self.last_outcome = None
        self._pending_intervention = False
```

`UNKNOWN` calls `hold_on_unknown`, which returns `None` and leaves the lock as it is (lines 101–107 and 152–153). The tier-1 UI button sends `reengaged` only when clicked (`frontend/src/components/intervention/AmbientCue.jsx` line 24). There is no `setTimeout` in that component.

The learner must respond with an accepted outcome, or the verdict must leave `DISTRACTED` (a `FOCUSED` observation calls `reset_on_focus`). A string `"acknowledged"` does neither.

### Cooldown when `last_intervention_at == 0`

The field is `last_intervention_at`, initialised to `0.0` (line 81). There is no field named `last_triggered_at`. The test is:

```163:164:backend/app/services/intervention_engine.py
        if ts - self.last_intervention_at < self.cooldown_seconds:
            return None
```

There is no branch that skips this when the stored time is 0.

Measured on a fresh engine, duration 8 s (level 1):

| `now` | Result |
|---|---|
| 10.0 | no intervention (`pending` stayed false) |
| 1700000000.0 | tier 1 `ambient_cue` |
| default `time.time()` | tier 1 `ambient_cue` (`last_intervention_at` became 1793105784.9788938) |

With a small clock, `10 - 0 < 30` is true, so the first 30 s are treated as already inside the cooldown. With wall-clock `time.time()`, `time.time() - 0` is greater than 30, so the first real heartbeat is not blocked. The clock-at-0 simulation of the 120 s episode fired one intervention: second 30, tier 3, `milestone_quiz`.

### Suggested minimal fixes (not applied)

Tier 2 is unreachable in the measured default runs. Two separate mechanisms cause that.

1. Pending lock. After the tier-1 cue at second 6, `_pending_intervention` stays true until an accepted `record_outcome` or a `FOCUSED` reset. A continuous `DISTRACTED` stream with no accepted response never reaches tier 2. A minimal change is to leave `_pending_intervention` false when the fired type is `ambient_cue`, since that cue has no timeout and the button is optional. The log can still record a later click.

2. Cooldown versus the tier-2 band. The band for level 2 is 10 s up to 20 s (`distraction_level_from_duration`). The first cue in the wall-clock simulation is at duration 6 s. The next decision that passes both the pending lock and the 30 s cooldown is at duration 36 s, which is level 3, so the engine selects tier 3. That happened for both `ignored` and `reengaged`. A minimal change that stays inside the existing bands is to not start the 30 s cooldown on a tier-1 ambient cue (`last_intervention_at` updated only for tiers 2–4), so a later heartbeat can still fall inside 10–20 s.

The enabled-tier fallback cannot select a higher tier than requested. It only decrements. No change is indicated for an upward jump. With tiers `{3, 4}` and a 6 s episode, the measured result is that nothing fires.

## 10. Audio / noise

The walk that produced `evaluation/thesis_numbers/raw/audio_noise_references.txt` (280 lines) used this pattern on `.py`, `.js`, `.jsx`, and `.md`, skipping `venv`, `venvpy312`, `node_modules`, `.git`, and `evaluation`:

`model3|M3|microphone|decibel|noise|dBFS|AudioContext|getUserMedia`

That file is the line listing. `apps/fastapi/routers/audio.py` is a one-line comment (`# Audio Router`) and does not match the pattern; it was read directly and loads nothing.

**(a) Is any audio model loaded at runtime? No.**

`models/src/model3_audio/` is seven one-line comments (`model.py`, `train.py`, `eval.py`, `infer.py`, `prepare.py`, `dataset.py`, `test/quick_test.py`) plus `test/README.md`. `MLService._init_models` loads the gaze checkpoint, the pose checkpoint, the engagement pickle, the fusion pickle, and a MediaPipe pose landmarker. It does not import `model3_audio`. `backend/app/services/noise_monitor.py` line 2 states the monitor is loudness only, with no audio model and no audio I/O.

**(b) Is there reachable frontend or backend code that measures microphone level and shows a noise notice? Yes.**

Measurement: `frontend/src/hooks/useMonitoringSession.js` lines 105–119 compute RMS dBFS from an `AnalyserNode`, and lines 157–164 open the microphone with echo cancellation, noise suppression, and auto gain off. Line 230 sends `noise_dbfs` on the heartbeat.

Notice: `backend/app/routes/session.py` lines 582–590 call `NoiseMonitor.update` and, when it returns true, `InterventionEngine.consider_noise`, which builds `environment_noise_notice`. `frontend/src/components/intervention/InterventionOverlay.jsx` lines 66–68 render `NoiseNotice`. That overlay is mounted from `VideoLearningPlayer.jsx`, `SubjectDetail.jsx`, and `QuizAttempt.jsx`.

`GamifiedBreak.jsx` lines 30–32 use `AudioContext` for an optional beep. That path does not read the microphone.

## 11. Thesis code listings vs the repository

The thesis source with the simplified listings was not in this repository (`evaluate_heartbeat_frame`, `process_verdict`, and `compute_observed_coverage_v1` do not occur as symbols). The comparison below is the real behaviour of the nearest functions, including the rolling-buffer question.

### `useMonitoringSession.js` heartbeat loop

The loop is `startTelemetryLoop` (`frontend/src/hooks/useMonitoringSession.js` lines 209–263). Every `intervalMs` (default 2000) it skips the tick if a request is already in flight, captures a 224×224 JPEG at quality 0.5, and POSTs `{image, is_quiz_context, noise_dbfs, lesson_audio_active}`. If `verdict === 'UNKNOWN'` it sets confidence to null (lines 236–237). There is no client-side rolling buffer of frames or probabilities, so nothing on the client is cleared on `UNKNOWN`.

### `evaluate_heartbeat_frame`

That name is not in the backend. The heartbeat route calls `MLService.predict_frame_image` (`backend/app/routes/session.py` lines 515–517).

The rolling buffer is **not** cleared on `UNKNOWN`. `predict_frame_image` appends gaze probabilities, pose, and landmarks first (`ml_service.py` lines 660–664). The no-face return happens after that append (lines 675–681) and does not pop or clear the deques. `clear_session` (lines 296–299) drops the buffer when a session is closed, not when a frame is `UNKNOWN`. The next face frame is scored with a window that still contains the preceding no-face frame’s gaze vector and pose. Those no-face frames still ran the gaze and pose networks inside `_infer_frame_signals` before the unknown return.

### `process_verdict`

That name is not in the engine. The route calls `decide_intervention` (`session.py` lines 570–576) with `observation_state` set to the verdict.

`UNKNOWN` calls `hold_on_unknown` and does not reset escalation or clear a pending intervention. `FOCUSED` calls `reset_on_focus`, which does clear the pending lock. `DISTRACTED` can fire a new intervention only when nothing is pending and the cooldown has elapsed.

### `compute_observed_coverage_v1`

That name is not in `observation_coverage.py`. The function is `compute_coverage_from_observations`. `UNKNOWN` is not in `VALID_STATES` (only `FOCUSED` and `DISTRACTED`, line 26). Samples whose state is not in that set are skipped at line 132, so they add neither focused nor distracted seconds. Uncovered session time becomes `unknown_seconds` (line 152). A separate helper, `episode_close_on_unknown` (lines 169–174), returns the unknown observation’s timestamp; the session route uses that idea to close an open distraction episode on `UNKNOWN` rather than treating it as re-engagement (`session.py` `upsert_distraction_episode`).

## Could not run

- Pose per-epoch validation-loss log. `run_model_metrics.py` found no pose log file under `models/outputs`. The checkpoint fields `epoch=3` and `best_val=6.01516703932612` were read. A quoted line that epoch 3 of 10 had the lowest validation loss does not exist on disk.
- Fresh forward pass of the epoch-15 gaze checkpoint on `natural.mp4`. Section 7 uses `window_preds_natural.csv` (local mtime 2026-02-17). The loaded gaze file’s local mtime is 2026-10-21. The argmax counts and mean `p_center` in section 7 are the stored CSV, not a new epoch-15 inference.
- Developer webcam protocol in section 8. The script is written. It needs a person at the laptop, so it was not started. No phase table was produced.
- Thesis listing diff. The simplified listings named in the prompt are not files in this repository, so a textual match against the thesis could not be executed. Section 11 reports the functions that are actually in the tree.
- First heartbeat latency posting. It is saved as `raw/heartbeat_latency_rejected_preresize_filter.json`. On that run, 29 of 50 timed responses had `reason=no_face`, so those times are not the full model path. Section 5 uses the second run, where `n_face_detected_true` is 50 and `n_reason_no_face` is 0.
