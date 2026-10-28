"""S3 runtime: fusion threshold env, body_no_face, session pose baseline."""

from __future__ import annotations

import base64

import cv2
import numpy as np
import pytest

from app.services.ml_service import MLService


def _jpeg_b64(frame: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def _person_landmarks() -> dict:
    return {
        "nose_x": 0.5,
        "nose_y": 0.4,
        "nose_vis": 0.9,
        "l_shoulder_x": 0.4,
        "l_shoulder_y": 0.55,
        "l_shoulder_vis": 0.9,
        "r_shoulder_x": 0.6,
        "r_shoulder_y": 0.55,
        "r_shoulder_vis": 0.85,
        "l_elbow_x": 0.35,
        "l_elbow_y": 0.7,
        "l_elbow_vis": 0.7,
        "r_elbow_x": 0.65,
        "r_elbow_y": 0.7,
        "r_elbow_vis": 0.7,
        "l_wrist_x": 0.3,
        "l_wrist_y": 0.8,
        "l_wrist_vis": 0.6,
        "r_wrist_x": 0.7,
        "r_wrist_y": 0.8,
        "r_wrist_vis": 0.6,
    }


class _FakeFusion:
    def __init__(self, dist_prob: float):
        self.dist_prob = dist_prob

    def predict_proba(self, _X):
        p = float(self.dist_prob)
        return np.array([[1.0 - p, p]], dtype=np.float64)


@pytest.fixture(autouse=True)
def _reset_ml_singleton():
    MLService._instance = None
    yield
    MLService._instance = None


def test_fusion_threshold_env_override(monkeypatch):
    monkeypatch.setenv("ML_FUSION_THRESHOLD", "0.80")
    MLService._instance = None
    svc = MLService()
    assert abs(svc.fusion_threshold - 0.80) < 1e-9


def test_fusion_threshold_flips_verdict_around_mock_prob():
    MLService._instance = None
    svc = MLService()
    svc.fusion_model = _FakeFusion(0.70)
    svc.fusion_threshold = 0.75
    svc.eng_model = None
    gaze = [np.array([0.8, 0.05, 0.05, 0.1], dtype=np.float32)]
    pose = [[5.0, 3.0, 0.0]]
    meta = {"face_detected": True, "gaze_label": "center"}
    verdict, _conf, feats = svc._score_window(gaze, pose, [None], meta, session_id="thr-lo")
    assert verdict == "FOCUSED"
    assert feats["distract_prob"] == 0.7

    svc.fusion_threshold = 0.65
    verdict2, _conf2, feats2 = svc._score_window(
        gaze, pose, [None], meta, session_id="thr-hi"
    )
    assert verdict2 == "DISTRACTED"
    assert feats2["distract_prob"] == 0.7


def test_body_no_face_distracted_does_not_append_buffer(monkeypatch):
    MLService._instance = None
    svc = MLService()
    sid = "body-noface"

    class _EmptyCascade:
        def detectMultiScale(self, *a, **k):
            return np.array([], dtype=np.int32).reshape(0, 4)

    svc.face_cascade = _EmptyCascade()
    monkeypatch.setattr(svc, "extract_landmarks", lambda *_a, **_k: _person_landmarks())

    before = len(svc._session_bufs[sid]["gaze"])
    frame = np.zeros((224, 224, 3), dtype=np.uint8)
    frame[:] = (40, 40, 40)
    verdict, conf, meta = svc.predict_frame_image(_jpeg_b64(frame), session_id=sid)
    assert verdict == "DISTRACTED"
    assert conf == 0.85
    assert meta.get("reason") == "body_no_face"
    assert meta.get("face_detected") is False
    assert meta.get("inference_path") == "body_no_face"
    assert len(svc._session_bufs[sid]["gaze"]) == before


def test_no_face_no_landmarks_still_unknown(monkeypatch):
    MLService._instance = None
    svc = MLService()
    sid = "noface-nobody"

    class _EmptyCascade:
        def detectMultiScale(self, *a, **k):
            return np.array([], dtype=np.int32).reshape(0, 4)

    svc.face_cascade = _EmptyCascade()
    monkeypatch.setattr(svc, "extract_landmarks", lambda *_a, **_k: None)

    frame = np.zeros((224, 224, 3), dtype=np.uint8)
    frame[:] = (40, 40, 40)
    verdict, conf, meta = svc.predict_frame_image(_jpeg_b64(frame), session_id=sid)
    assert verdict == "UNKNOWN"
    assert conf is None
    assert meta.get("reason") == "no_face"


def test_pose_baseline_locks_after_k_frames_and_centers():
    MLService._instance = None
    svc = MLService()
    svc.pose_baseline_frames = 4
    sid = "baseline-sess"
    for i in range(4):
        svc._update_pose_baseline(sid, [10.0 + i, -20.0 + i, 1.0])
    baseline = svc._session_pose_baseline.get(sid)
    assert baseline is not None
    yaw0, pitch0 = baseline
    # median of [10,11,12,13] = 11.5; median of [-20,-19,-18,-17] = -18.5
    assert abs(yaw0 - 11.5) < 1e-6
    assert abs(pitch0 - (-18.5)) < 1e-6

    centered, by, bp = svc._centered_pose_buf(sid, [[11.5, -18.5, 0.0], [21.5, -8.5, 2.0]])
    assert by == yaw0 and bp == pitch0
    assert abs(centered[0][0]) < 1e-6
    assert abs(centered[0][1]) < 1e-6
    assert abs(centered[1][0] - 10.0) < 1e-6
    assert abs(centered[1][1] - 10.0) < 1e-6


def test_landmarks_indicate_person_helper():
    assert MLService._landmarks_indicate_person(_person_landmarks()) is True
    assert MLService._landmarks_indicate_person(None) is False
    weak = _person_landmarks()
    weak["nose_vis"] = 0.1
    assert MLService._landmarks_indicate_person(weak) is False


def _lm_at(wrist_y: float) -> dict:
    """Minimal pose landmarks with controllable wrist height (for engagement features)."""
    return {
        "nose_x": 0.5,
        "nose_y": 0.35,
        "nose_vis": 0.9,
        "l_shoulder_x": 0.4,
        "l_shoulder_y": 0.5,
        "l_shoulder_vis": 0.9,
        "r_shoulder_x": 0.6,
        "r_shoulder_y": 0.5,
        "r_shoulder_vis": 0.9,
        "l_elbow_x": 0.35,
        "l_elbow_y": 0.65,
        "l_elbow_vis": 0.8,
        "r_elbow_x": 0.65,
        "r_elbow_y": 0.65,
        "r_elbow_vis": 0.8,
        "l_wrist_x": 0.3,
        "l_wrist_y": wrist_y,
        "l_wrist_vis": 0.8,
        "r_wrist_x": 0.7,
        "r_wrist_y": wrist_y,
        "r_wrist_vis": 0.8,
    }


def test_engagement_features_live_with_short_buffer():
    """With ≥2 landmarks, live buffers must not collapse to the constant default vector."""
    MLService._instance = None
    svc = MLService()
    assert svc.window_size >= 2

    still = [_lm_at(0.75), _lm_at(0.75), _lm_at(0.75)]
    moving = [_lm_at(0.55), _lm_at(0.80), _lm_at(0.45)]

    f_still = svc.compute_engagement_features(still)
    f_move = svc.compute_engagement_features(moving)

    # Defaults used only when n < 2; both buffers have n=3.
    assert f_still["lw_speed_mean"] == 0.0
    assert f_move["lw_speed_mean"] > 0.0
    assert f_still["nose_jitter"] == 0.0 or f_still["nose_jitter"] >= 0.0
    assert f_move != f_still

    if svc.eng_model is not None and svc.eng_feature_cols:
        import numpy as np

        def _prob(feats):
            X = np.array(
                [[feats.get(c, 0.0) for c in svc.eng_feature_cols]],
                dtype=np.float32,
            )
            return float(svc.eng_model.predict_proba(X)[0, 1])

        p_still = _prob(f_still)
        p_move = _prob(f_move)
        assert p_still != p_move

    # Single landmark still falls back to defaults.
    one = svc.compute_engagement_features([_lm_at(0.7)])
    assert one["lw_to_nose_mean"] == 0.5
    assert one["lw_speed_mean"] == 0.0
    MLService._instance = None
