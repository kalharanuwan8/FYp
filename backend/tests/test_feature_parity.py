"""Training/live feature parity for model6.

The live scorer (models/src/features/live.py) must produce exactly the window
features that offline extraction (windows.windows_from_frames) produces from
the same frames — otherwise the model is evaluated on one feature space and
deployed on another (the v2 failure mode).
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from models.src.features.face_pose import FrameFeatures
from models.src.features.live import LiveWindowScorer
from models.src.features.windows import (
    WINDOW_FEATURE_NAMES,
    compute_pose_baseline,
    windows_from_frames,
)

FPS = 2.0
WINDOW_SEC = 5.0


class _ReplayExtractor:
    """Stands in for FrameFeatureExtractor: returns precomputed frame features."""

    def __init__(self, frames):
        self._frames = list(frames)
        self._i = 0

    def process(self, _frame, t_sec):
        f = self._frames[self._i]
        assert abs(f.t_sec - t_sec) < 1e-9
        self._i += 1
        return f

    def close(self):
        pass


def _synthetic_frames(n=80, seed=7):
    rng = np.random.default_rng(seed)
    frames = []
    for i in range(n):
        face = bool(rng.random() > 0.15)
        frames.append(
            FrameFeatures(
                t_sec=i / FPS,
                face_present=face,
                yaw=float(rng.normal(0, 15)),
                pitch=float(rng.normal(0, 10)),
                roll=float(rng.normal(0, 5)),
                iris_x=float(rng.uniform(0.2, 0.8)),
                iris_y=float(rng.uniform(0.2, 0.8)),
                blink=float(rng.uniform(0, 1)),
                jaw_open=float(rng.uniform(0, 0.5)),
                hand_to_face=float(rng.uniform(0, 1)),
                body_motion=float(rng.uniform(0, 0.02)),
                nose_x=0.5,
                nose_y=0.4,
                body_present=True,
            )
        )
    return frames


def _assert_parity(frames):
    yaw0, pitch0, roll0 = compute_pose_baseline(frames, n_frames=30)
    offline = {
        round(w["window_start_sec"], 6): w
        for w in windows_from_frames(
            frames,
            window_sec=WINDOW_SEC,
            hop_sec=1.0 / FPS,
            yaw0=yaw0,
            pitch0=pitch0,
            roll0=roll0,
        )
    }
    scorer = LiveWindowScorer(
        window_sec=WINDOW_SEC, baseline_frames=30, extractor=_ReplayExtractor(frames)
    )
    compared = 0
    for f in frames:
        scorer.add_frame(f.t_sec, np.zeros((2, 2, 3), dtype=np.uint8))
        live = scorer.features()
        if live is None or not live["baseline_locked"]:
            continue  # offline uses the whole clip for the baseline; live only the past
        ref = offline[round(live["window_start_sec"], 6)]
        for name in WINDOW_FEATURE_NAMES:
            assert live[name] == pytest.approx(ref[name], abs=1e-9), name
        compared += 1
    return compared


def test_live_scorer_matches_offline_windows():
    assert _assert_parity(_synthetic_frames()) >= 20


def test_live_scorer_ignores_out_of_order_frames():
    frames = _synthetic_frames(n=12)
    scorer = LiveWindowScorer(window_sec=WINDOW_SEC, extractor=_ReplayExtractor(frames))
    dummy = np.zeros((2, 2, 3), dtype=np.uint8)
    assert scorer.add_frame(frames[0].t_sec, dummy) is not None
    assert scorer.add_frame(frames[0].t_sec, dummy) is None  # duplicate timestamp


@pytest.mark.skipif(
    not os.environ.get("MODEL6_PARITY_CLIP"),
    reason="set MODEL6_PARITY_CLIP=<video> to run parity on real MediaPipe output",
)
def test_parity_on_real_clip():
    """Real MediaPipe: extract per-frame features once, replay through both paths."""
    cv2 = pytest.importorskip("cv2")
    from models.src.features.face_pose import FrameFeatureExtractor
    from models.src.model6_natural.extract import _iter_sampled_frames

    clip = Path(os.environ["MODEL6_PARITY_CLIP"])
    ex = FrameFeatureExtractor()
    try:
        frames = [ex.process(img, t) for t, img in _iter_sampled_frames(clip, target_fps=FPS)]
    finally:
        ex.close()
    assert cv2 is not None
    assert _assert_parity(frames) > 0
