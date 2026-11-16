# PLAN 5 build scratchpad

## Delivered
- Step 0: `Model6SklearnWrapper.__setstate__` + defensive `_cal` (pack load OK)
- Step 1: `screen_gaze.py`, live calibration mapper, gaze dwell ≥2s ⇒ DISTRACTED, `gaze_debug`
- Step 1a FE: `ScreenCalibrationOverlay` (5-dot), hook 640@~15fps, calib_target/screen
- Step 2: T1 timeout 6s → force T2; T2/T3 = 20s; cooldown 20s; timeout callback wired
- Step 3: `useFullscreen` + video stage fullscreen (not native `<video>`)
- Step 4: Demo sidebar (`DEMO_MODE`), force bypass, gaze readout
- Step 5: Stop-session button, grade 1–12 filter, `cleanup_grades.py`

## Run with
```
set DEMO_MODE=true
venvpy312\Scripts\python.exe -m flask --app backend.wsgi run
```

## Manual checks
- No `Live scoring error: '_cal'`
- 5-dot calibration → Screen mapped ✓
- Look away 2s → DISTRACTED source=gaze_screen
- Leave T1 unanswered → T2 in 6–8s
- Demo buttons fire while another prompt is open
- Fullscreen: video + overlays only
