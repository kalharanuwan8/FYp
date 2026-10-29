# Thesis draft — condensed models + DSM-5 full-system indicators

Paste into methodology / testing / Appendix B as needed. Numbers are from `evaluation/thesis_numbers/REPORT.md` (thesis-final evaluation). This file is **not** the thesis document itself.

---

## Methodology — models (condensed)

Luma’s camera path is **one** behavioural signal among several. Four models support monitored **video/lesson** sessions only; they are not used alone to label a child as distracted.

| Model | Role | Headline result (REPORT.md) | Main weakness |
|---|---|---|---|
| M1 Gaze (MobileNetV2, 4 classes) | Eye-direction cue into fusion | Test accuracy **0.6017…**; validation macro-F1 peak in log **0.5698…** | Far above chance (25%) but modest absolute accuracy; live path may fall back without the checkpoint |
| M2 Head pose (ResNet-18) | Yaw/pitch/roll into fusion | BIWI test mean MAE **5.93°** (yaw/pitch/roll mean of three) | Best checkpoint stored at epoch index 3; no per-epoch log on disk |
| Engagement (sklearn on landmarks) | Activity proxy into fusion | Hold-out accuracy **0.9737…**, macro-F1 **0.9732…** | Labels are weak/heuristic rules — scores measure agreement with those rules |
| Fusion (logistic, 9 features) | Combines gaze/pose/engagement → P(distracted) | Stratified test Acc/P/R/F1/ROC all **1.0** (n=120) | Documented **ISSUE (leakage)** historically; not a clean participant-independent claim |

**Scope.** Webcam fusion runs during monitored video. Quizzes and reading documents use **other** signals (below). Noise loudness is a separate on-device RMS cue (no audio model).

---

## Methodology — full system (DSM-5 inattention proxies)

Distraction / inattention evidence is a **per-indicator profile**, not a single overall “distracted” label. Indicators are **record-only** for teacher reporting (existing webcam/noise interventions for video sessions are unchanged).

| ID | DSM-5 wording (proxy) | How Luma measures it | Where it applies |
|---|---|---|---|
| DSM-1 | Difficulty sustaining attention | Idle ≥ **15 s** with no click, key, touch or scroll | Quiz and **document** pages only (not video) |
| DSM-2 | Easily distracted by external stimuli | Camera DISTRACTED episodes **and/or** sustained room-noise notice | Monitored **video/lesson** sessions (camera); noise on heartbeat |
| DSM-3 | Fails to finish | Quiz open longer than teacher **time limit**, or unfinished after the limit | Quizzes with `time_limit_minutes` set |
| DSM-4 | Careless mistakes | ≥ **3** consecutive wrong answers on questions tagged **easy** | Quizzes |
| DSM-5 | Does not seem to listen | Teacher **hint** opened on **every** question (≥ 3 questions) | Quizzes |
| DSM-6 | Avoids sustained mental effort | Error rate ≥ **70%** and median answer time &lt; **5 s** | Quizzes |
| DSM-7 | Forgetful in daily activities | Day’s focused session minutes &lt; student’s **daily goal** | Last 7 calendar days excluding today |

Disclaimer for UI and thesis: these are **behavioural proxies aligned with DSM-5 inattention descriptions**, not a clinical diagnosis.

---

## Testing — models (one summary table)

| Model | Metric | Value | Flag / note |
|---|---|---|---|
| M1 | Test accuracy | 0.6017… | Above chance |
| M1 | Val macro-F1 (log peak) | 0.5698… | — |
| M2 | Test mean MAE (°) | 5.93… | — |
| Engagement | Hold-out accuracy / macro-F1 | 0.9737… / 0.9732… | Weak labels |
| Fusion (M5) | Stratified Acc / F1 | 1.0 / 1.0 | **ISSUE: leakage** — treat carefully in discussion |

Long per-model appendix material can be replaced by this table (see Appendix B below).

---

## Testing — system (per indicator)

Automated coverage: `backend/tests/test_dsm_indicators.py` (positive and negative cases for DSM-1…7, plus teacher access control). Manual: teacher opens **Students → DSM-5 indicators** after a quiz/document session that generates idle, hints, or overtime.

---

## Appendix B — short model metrics (replacement for long evaluation appendix)

| Model | File (when present) | Key number | Caveat |
|---|---|---|---|
| Gaze | `model1_gaze/best.pt` | Acc 0.60; macro-F1 ~0.56 | Checkpoint may be absent on a given machine |
| Pose | `model2_pose/best.pt` | MAE 5.93° | Epoch field = 3 |
| Engagement | `model4_engagement/model.pkl` | Acc 0.97 | Weak labels |
| Fusion | `model5_fusion/model.pkl` | Acc 1.0 on stratified test | Leakage / not participant-independent |

**System claim (preferred for the thesis).** Luma concludes inattention risk from **multiple** signals. The camera is **DSM-2 only** and only during video; quizzes and documents contribute DSM-1 and DSM-3–6; daily goals contribute DSM-7.
