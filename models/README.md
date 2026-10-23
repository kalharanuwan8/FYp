# Distraction models

Research training/inference code for gaze, head pose, engagement, and fusion.

**For live web-app monitoring**, see [CHECKPOINTS.md](CHECKPOINTS.md). The Flask backend loads these checkpoints in-process via `backend/app/services/ml_service.py` on each session heartbeat.

Standalone webcam test (desktop OpenCV window):

```bash
python webcam_test.py
```
