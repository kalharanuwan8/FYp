"""
Static regressions for Phase-1 script/demo defects that live outside pytest
fixtures (models evaluation harnesses).
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS = REPO_ROOT / "models"


def test_fusion_video_has_no_filename_probability_override():
    """
    Demonstration harness must not replace Model 5 probabilities from the
    input filename. Filename-derived weak labels in prep.py are a separate
    training-data concern and are not independent ground truth.
    """
    src = (MODELS / "test_fusion_video.py").read_text(encoding="utf-8")
    assert "dist_prob = min(dist_prob, 0.15)" not in src
    assert "dist_prob = max(dist_prob, 0.88)" not in src
    assert "Direct video-based override" not in src


def test_run_tests_fusion_summary_defines_threshold_f1():
    """Fusion summary must not reference an unbound f12 when threshold == 0.5."""
    src = (MODELS / "run_tests.py").read_text(encoding="utf-8")
    assert "f1_thr" in src
    # Old crash pattern: print used {f12} without assigning it when untuned.
    assert "F1@{threshold:.2f}={f12:.4f}" not in src
