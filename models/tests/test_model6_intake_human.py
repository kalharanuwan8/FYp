"""Intake discovery + human-label segment helpers (no MediaPipe)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from models.src.model6_natural.extract import (  # noqa: E402
    default_segments,
    label_from_segments,
    merge_annotation_segments,
)
from models.src.model6_natural.intake import (  # noqa: E402
    DEFAULT_RAW_ROOT,
    _find_by_stem,
    _find_focused,
    _participant_id,
)
from models.src.model6_natural.train import _fit_mask  # noqa: E402
import pandas as pd  # noqa: E402


def test_participant_id_parsing():
    assert _participant_id("participant 1") == "S01"
    assert _participant_id("Participant 7") == "S07"
    assert _participant_id("dataset") is None


def test_case_insensitive_stem_match(tmp_path: Path):
    (tmp_path / "Focused.mp4").write_bytes(b"x")
    (tmp_path / "NATURAL.MOV").write_bytes(b"x")
    assert _find_by_stem(tmp_path, "focused").name == "Focused.mp4"
    assert _find_by_stem(tmp_path, "natural").name == "NATURAL.MOV"
    assert _find_focused(tmp_path).name == "Focused.mp4"


def test_merge_annotation_overlays_default():
    base = default_segments("distracted", 100.0)
    overlays = [(10.0, 25.0, "focused", 0), (60.0, 70.0, "focused", 0)]
    segs = merge_annotation_segments(base, overlays)
    assert label_from_segments(segs, 0.0, 5.0) == (1, "distracted")
    assert label_from_segments(segs, 12.0, 5.0) == (0, "focused")
    assert label_from_segments(segs, 62.0, 5.0) == (0, "focused")
    assert label_from_segments(segs, 80.0, 5.0) == (1, "distracted")
    # Straddle overlay boundary with both sides < 0.6 cover → drop
    assert label_from_segments(segs, 7.5, 5.0)[0] is None


def test_distraction_spans_policy_drops_unlabelled_distracted():
    from models.src.model6_natural.extract import distraction_span_segments

    # Distracted clip: unmarked = dropped; D span → 1; F span → 0
    segs = distraction_span_segments(
        "distracted",
        100.0,
        [(10.0, 20.0, "distracted", 1), (40.0, 50.0, "focused", 0)],
    )
    assert label_from_segments(segs, 0.0, 5.0)[0] is None  # unlabelled
    assert label_from_segments(segs, 12.0, 5.0) == (1, "distracted")
    assert label_from_segments(segs, 42.0, 5.0) == (0, "focused")

    # Focused clip: unmarked = 0; D span → 1
    segs_f = distraction_span_segments("focused", 100.0, [(30.0, 40.0, "distracted", 1)])
    assert label_from_segments(segs_f, 0.0, 5.0) == (0, "focused")
    assert label_from_segments(segs_f, 32.0, 5.0) == (1, "distracted")


def test_fit_mask_excludes_eval_only():
    df = pd.DataFrame(
        {
            "y": [0, 1, 0, 1],
            "eval_only": [0, 0, 1, 1],
            "condition": ["focused", "distracted", "natural", "natural"],
        }
    )
    mask = _fit_mask(df)
    assert mask.tolist() == [True, True, False, False]


def test_discover_clips_seven_subjects():
    if not DEFAULT_RAW_ROOT.exists():
        pytest.skip("raw data not mounted")
    from models.src.model6_natural.intake import discover_clips

    clips = discover_clips(DEFAULT_RAW_ROOT, probe=False)
    subjects = sorted({c.subject_id for c in clips if c.condition != "protocol"})
    assert subjects == [f"S{i:02d}" for i in range(1, 8)]
    by = {(c.subject_id, c.condition): c.path.name for c in clips if c.condition != "protocol"}
    assert by[("S05", "focused")].lower() == "focused.mov"
    assert by[("S07", "focused")].lower() == "focused.mp4"
    assert by[("S07", "natural")].lower() == "natural.mp4"
    assert by[("S02", "focused")].lower() == "forced.mp4"
