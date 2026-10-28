"""Face-gate: no-face buffer rule and box coordinate mapping."""

from __future__ import annotations

import base64

import cv2
import numpy as np

from app.services.ml_service import MLService


def _jpeg_b64(frame: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def test_no_face_unknown_does_not_append_to_session_buffer():
    MLService._instance = None
    svc = MLService()
    sid = "face-gate-noface"
    before = {
        "gaze": len(svc._session_bufs[sid]["gaze"]),
        "pose": len(svc._session_bufs[sid]["pose"]),
        "lm": len(svc._session_bufs[sid]["lm"]),
    }
    frame = np.zeros((224, 224, 3), dtype=np.uint8)
    frame[:] = (40, 40, 40)
    verdict, conf, meta = svc.predict_frame_image(_jpeg_b64(frame), session_id=sid)
    assert verdict == "UNKNOWN"
    assert conf is None
    assert meta.get("reason") == "no_face"
    assert meta.get("face_detected") is False
    after = svc._session_bufs[sid]
    assert len(after["gaze"]) == before["gaze"]
    assert len(after["pose"]) == before["pose"]
    assert len(after["lm"]) == before["lm"]
    MLService._instance = None


def test_detect_face_maps_box_to_original_coords_when_upscaling():
    MLService._instance = None
    svc = MLService()
    svc.face_upscale = 2.0
    svc.face_min_neighbors = 5
    svc.face_min_size = 50
    svc.face_equalize = False

    class _FakeCascade:
        def detectMultiScale(self, gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50)):
            h, w = gray.shape[:2]
            assert h == 448 and w == 448
            # Box on the upscaled image → maps to (50,40,60,60) on 224×224.
            return np.array([[100, 80, 120, 120]], dtype=np.int32)

    svc.face_cascade = _FakeCascade()
    frame = np.zeros((224, 224, 3), dtype=np.uint8)
    frame[:] = (80, 80, 80)
    box = svc._detect_face(frame)
    assert box == (50, 40, 60, 60)

    class _EmptyCascade:
        def detectMultiScale(self, *a, **k):
            return np.array([], dtype=np.int32).reshape(0, 4)

    svc.face_cascade = _EmptyCascade()
    assert svc._detect_face(frame) is None
    MLService._instance = None


def test_detect_face_default_min_size_matches_face_gate_check():
    MLService._instance = None
    svc = MLService()
    assert svc.face_min_size == 28
    assert svc.face_min_neighbors == 5
    assert abs(svc.face_upscale - 1.0) < 1e-9
    assert svc.face_equalize is False
    MLService._instance = None
