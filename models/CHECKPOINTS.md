# Model checkpoints for live monitoring

The Flask `MLService` loads these files at startup (paths relative to the `models/` directory):

| Model | Default path | Env override |
|-------|--------------|--------------|
| Gaze (M1) | `outputs/checkpoints/model1_gaze/best.pt` | `GAZE_CKPT` |
| Head pose (M2) | `outputs/checkpoints/model2_pose/best.pt` | `POSE_CKPT` |
| Engagement (M4) | `outputs/checkpoints/model4_engagement/model.pkl` | `ENG_CKPT` |
| Fusion (M5) | `outputs/checkpoints/model5_fusion/model.pkl` | `FUSION_CKPT` |
| MediaPipe task | `src/model4_engagement/pose_landmarker_lite.task` | (fixed path) |

## How live monitoring works

1. Browser opens the webcam and sends JPEG frames every ~2s to `POST /api/session/<id>/heartbeat` with `{ "image": "data:image/jpeg;base64,..." }`.
2. Backend `MLService.predict_frame_image` runs gaze + pose + engagement, aggregates a short window, then scores with Model 5 fusion (or a heuristic gate if fusion weights are missing).
3. Heartbeat response includes `verdict`, `confidence`, and `ml_mode` (`full` | `partial` | `fallback`).

## Setup

```bash
# From repo root — place trained weights here (train via models/src/*/train.py if needed)
mkdir -p models/outputs/checkpoints/model1_gaze
mkdir -p models/outputs/checkpoints/model2_pose
mkdir -p models/outputs/checkpoints/model4_engagement
mkdir -p models/outputs/checkpoints/model5_fusion

# Optional local smoke test (same weights)
cd models
python webcam_test.py --window-sec 3
# Or video fusion (uses real Model 5):
python test_fusion_video.py --input path/to/video.mp4
```

If checkpoints are missing, the backend still starts and reports `ml_mode: "fallback"` (OpenCV Haar heuristics). Place the four weight files above to get `ml_mode: "full"`.

Verified locally: with all four checkpoints present, `MLService` logs `ml_mode=full` and blank (no-face) heartbeat frames return `DISTRACTED` with `ml_mode` in the JSON response.

Optional window size (heartbeat frames aggregated before fusion):

```bash
set ML_WINDOW_FRAMES=3
```
