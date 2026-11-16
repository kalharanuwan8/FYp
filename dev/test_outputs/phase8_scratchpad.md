# PLAN 8 gaze accuracy — scratchpad

## Delivered
- **A** `face_pose.py`: `look_h` / `look_v` / `look_down`; iris_y vs corner midline
- **B** `is_blink`: blink && look_down < 0.4 (looking down ≠ blink)
- **C** mapper: per-frame trimmed fit with look terms; margin 0.03; head phase; freeze head if missing
- **D** `INTERVENTION_T1_SEC=3`; gaze dwell ≤ T1; episode backdate; HB interval 1 s
- **E** `GazeSelfTest.jsx`; head phase in calibration; `onHeartbeat`; eval `gaze test`

## Manual
```
set DEMO_MODE=true
set INTERVENTION_T1_SEC=3
venvpy312\Scripts\python.exe -m flask --app backend.wsgi run
```
Calibrate (incl. head turn) → Test it → all 6 ✓ → eyes past left edge → T1 in ~3–4 s.

## Tests
`models/tests` + gaze timing + intervention engine/v4 under venvpy312.
