"""PLAN 6: criteria-table evidence rules (backend/app/services/distraction_evidence.py)."""
import pytest

from app.services.distraction_evidence import (
    DISTRACTED,
    FOCUSED,
    NORMAL,
    RULE_A_ABSENT,
    RULE_A_TAB,
    RULE_B_MULTI,
    RULE_C_STRONG,
    STRONG,
    WARNING,
    EvidenceTracker,
)

FOCUSED_FRAME = dict(gaze_off=False, head_away=False, face_present=True, body_present=True)


def run(tracker, t0, t1, step=0.5, **signals):
    """Feed identical signals every ``step`` s over [t0, t1]; return all results."""
    out = []
    n = int(round((t1 - t0) / step))
    for i in range(n + 1):
        out.append(tracker.update(t0 + i * step, **signals))
    return out


def first_distracted_at(results, t0, step=0.5):
    for i, r in enumerate(results):
        if r.verdict == DISTRACTED:
            return t0 + i * step
    return None


# ---------------------------------------------------------------- gaze row
def test_gaze_brief_glance_is_normal():
    tr = EvidenceTracker()
    run(tr, 0, 5, **FOCUSED_FRAME)
    res = run(tr, 5.5, 7.5, gaze_off=True, head_away=False, face_present=True, body_present=True)
    assert all(r.levels["gaze"] == NORMAL for r in res)
    assert all(r.verdict == FOCUSED for r in res)


def test_gaze_three_to_five_seconds_is_warning_only():
    tr = EvidenceTracker()
    res = run(tr, 0, 4.5, gaze_off=True, head_away=False, face_present=True, body_present=True)
    assert res[-1].levels["gaze"] == WARNING
    assert all(r.verdict == FOCUSED for r in res)


def test_gaze_over_five_seconds_repeated_is_strong():
    tr = EvidenceTracker()
    away = dict(gaze_off=True, head_away=False, face_present=True, body_present=True)
    run(tr, 0, 4, **away)  # first qualifying episode (4 s)
    run(tr, 4.5, 10, **FOCUSED_FRAME)
    res = run(tr, 10.5, 16.5, **away)  # second, now > 5 s
    assert res[-1].levels["gaze"] == STRONG


def test_gaze_over_five_seconds_once_is_not_strong():
    tr = EvidenceTracker()
    res = run(tr, 0, 6, gaze_off=True, head_away=False, face_present=True, body_present=True)
    assert res[-1].levels["gaze"] == WARNING


def test_gaze_dwell_backdates_run_start():
    tr = EvidenceTracker()
    r = tr.update(10.0, gaze_off=True, gaze_off_dwell_sec=3.5, face_present=True, body_present=True)
    assert r.levels["gaze"] == WARNING


# ---------------------------------------------------------------- head row
def test_head_quick_turn_normal_long_turn_warning():
    tr = EvidenceTracker()
    res = run(tr, 0, 2, gaze_off=False, head_away=True, face_present=True, body_present=True)
    assert res[-1].levels["head"] == NORMAL
    res = run(tr, 2.5, 3.5, gaze_off=False, head_away=True, face_present=True, body_present=True)
    assert res[-1].levels["head"] == WARNING


# ---------------------------------------------------------------- face row
def test_face_missing_under_two_seconds_is_normal():
    tr = EvidenceTracker()
    res = run(tr, 0, 1.5, face_present=False, body_present=True)
    assert res[-1].levels["face"] == NORMAL


def test_face_missing_two_to_three_seconds_is_warning():
    tr = EvidenceTracker()
    res = run(tr, 0, 2.5, face_present=False, body_present=True)
    assert res[-1].levels["face"] == WARNING
    assert res[-1].verdict == FOCUSED


# ---------------------------------------------------------------- noise row
def test_single_noise_spike_is_normal():
    tr = EvidenceTracker()
    r = tr.update(0, noise_spike=True, **FOCUSED_FRAME)
    r = tr.update(1, **FOCUSED_FRAME)
    assert r.levels["noise"] == NORMAL
    assert r.verdict == FOCUSED


def test_repeated_noise_spikes_warning_then_strong_with_gaze_away():
    tr = EvidenceTracker()
    for t in (0, 5, 10):
        r = tr.update(t, noise_spike=True, **FOCUSED_FRAME)
    assert r.levels["noise"] == WARNING
    res = run(tr, 10.5, 14, gaze_off=True, head_away=False, face_present=True, body_present=True)
    assert res[-1].levels["noise"] == STRONG


def test_noise_spikes_expire_after_window():
    tr = EvidenceTracker()
    for t in (0, 1, 2):
        tr.update(t, noise_spike=True, **FOCUSED_FRAME)
    r = tr.update(70, **FOCUSED_FRAME)
    assert r.levels["noise"] == NORMAL


# ---------------------------------------------------------------- idle row
@pytest.mark.parametrize(
    "idle,expected", [(5.0, NORMAL), (8.5, WARNING), (12.0, WARNING)]
)
def test_idle_levels_without_gaze_away(idle, expected):
    tr = EvidenceTracker()
    r = tr.update(20, idle_sec=idle, **FOCUSED_FRAME)
    assert r.levels["idle"] == expected


def test_idle_over_ten_seconds_with_gaze_away_is_strong():
    tr = EvidenceTracker()
    res = run(tr, 0, 4, gaze_off=True, head_away=False, face_present=True, body_present=True,
              idle_sec=12.0)
    assert res[-1].levels["idle"] == STRONG


def test_idle_ignored_while_video_playing():
    tr = EvidenceTracker()
    res = run(tr, 0, 30, idle_sec=30.0, video_playing=True, **FOCUSED_FRAME)
    assert all(r.levels["idle"] == NORMAL for r in res)
    assert all(r.verdict == FOCUSED for r in res)


# ------------------------------------------------- skipping / quiz / hints
def test_forward_skips_warning_then_strong_with_gaze():
    tr = EvidenceTracker()
    tr.update(0, seek_forward_events=1, **FOCUSED_FRAME)
    r = tr.update(5, seek_forward_events=1, **FOCUSED_FRAME)
    assert r.levels["skipping"] == WARNING
    res = run(tr, 5.5, 9, gaze_off=True, head_away=False, face_present=True, body_present=True)
    assert res[-1].levels["skipping"] == STRONG


def test_error_streak_and_hint_repeats():
    tr = EvidenceTracker()
    r = tr.update(0, quiz_wrong_streak=2, hint_repeats=1, **FOCUSED_FRAME)
    assert r.levels["quiz_errors"] == NORMAL and r.levels["hints"] == NORMAL
    r = tr.update(1, quiz_wrong_streak=3, hint_repeats=2, **FOCUSED_FRAME)
    assert r.levels["quiz_errors"] == WARNING and r.levels["hints"] == WARNING
    r = tr.update(2, quiz_wrong_streak=3, hint_repeats=2, idle_sec=9.0, **FOCUSED_FRAME)
    assert r.levels["quiz_errors"] == STRONG and r.levels["hints"] == STRONG


# ---------------------------------------------- acceptance scenarios (§2)
def test_phone_look_down_detected_by_multi_signal_at_five_seconds():
    tr = EvidenceTracker()
    run(tr, 0, 10, **FOCUSED_FRAME)
    res = run(tr, 10.5, 18.5, gaze_off=True, head_away=True, face_present=True, body_present=True)
    t = first_distracted_at(res, 10.5)
    assert t is not None and 15.0 <= t <= 16.0
    assert res[-1].rule == RULE_B_MULTI


def test_turn_to_talk_six_seconds_is_distracted():
    tr = EvidenceTracker()
    res = run(tr, 0, 6, gaze_off=True, head_away=True, face_present=True, body_present=True)
    assert res[-1].verdict == DISTRACTED
    assert res[-1].rule == RULE_B_MULTI


def test_leaving_seat_is_override():
    tr = EvidenceTracker()
    run(tr, 0, 5, **FOCUSED_FRAME)
    res = run(tr, 5.5, 11, face_present=False, body_present=False)
    t = first_distracted_at(res, 5.5)
    assert t is not None and t <= 11.0
    assert res[-1].rule == RULE_A_ABSENT


def test_tab_hidden_is_override():
    tr = EvidenceTracker()
    r = tr.update(0, tab_hidden_sec=2.0)
    assert r.verdict == FOCUSED
    r = tr.update(1, tab_hidden_sec=3.0)
    assert r.verdict == DISTRACTED and r.rule == RULE_A_TAB


def test_window_blur_needs_five_seconds():
    tr = EvidenceTracker()
    assert tr.update(0, window_blur_sec=4.0).verdict == FOCUSED
    assert tr.update(1, window_blur_sec=5.0).rule == RULE_A_TAB


def test_long_stare_away_single_strong_after_ten_seconds():
    tr = EvidenceTracker()
    res = run(tr, 0, 12, gaze_off=True, head_away=False, face_present=True, body_present=True)
    t = first_distracted_at(res, 0)
    assert t is not None and 10.0 <= t <= 10.5
    assert res[-1].rule == RULE_C_STRONG


def test_noisy_room_plus_looking_around_is_distracted():
    tr = EvidenceTracker()
    for t in (0, 3, 6):
        tr.update(t, noise_spike=True, **FOCUSED_FRAME)
    res = run(tr, 6.5, 13, gaze_off=True, head_away=False, face_present=True, body_present=True)
    assert res[-1].verdict == DISTRACTED


def test_look_away_four_seconds_once_stays_focused():
    tr = EvidenceTracker()
    res = run(tr, 0, 4, gaze_off=True, head_away=True, face_present=True, body_present=True)
    res += run(tr, 4.5, 10, **FOCUSED_FRAME)
    assert all(r.verdict == FOCUSED for r in res)
    assert res[len(res) // 4].levels["gaze"] in (NORMAL, WARNING)


def test_watching_video_without_input_stays_focused():
    tr = EvidenceTracker()
    res = run(tr, 0, 30, idle_sec=None, video_playing=True, **FOCUSED_FRAME)
    res += run(tr, 30.5, 40, idle_sec=35.0, video_playing=True, **FOCUSED_FRAME)
    assert all(r.verdict == FOCUSED for r in res)


# ------------------------------------------------------ robustness
def test_missing_observation_does_not_break_run_briefly():
    tr = EvidenceTracker()
    run(tr, 0, 2, gaze_off=True, head_away=True, face_present=True, body_present=True)
    tr.update(3.0)  # no observation this heartbeat
    res = run(tr, 4, 6, gaze_off=True, head_away=True, face_present=True, body_present=True)
    assert res[-1].verdict == DISTRACTED


def test_long_gap_ends_run():
    tr = EvidenceTracker()
    run(tr, 0, 2, gaze_off=True, face_present=True, body_present=True)
    r = tr.update(6.0, gaze_off=True, face_present=True, body_present=True)
    assert r.pattern_sec.get("gaze") is None or r.pattern_sec["gaze"] < 1.0


def test_model_probability_fused_and_exposed():
    tr = EvidenceTracker()
    r = tr.update(0, p_model=0.8, **FOCUSED_FRAME)
    assert r.p_rules == 0.0 and r.p_fused == 0.8
    assert r.verdict == FOCUSED  # model alone is not rule evidence
    d = r.as_dict()
    assert set(d) >= {"verdict", "rule", "evidence", "p_rules", "p_fused", "reasons"}


def test_reset_clears_state():
    tr = EvidenceTracker()
    run(tr, 0, 6, gaze_off=True, head_away=True, face_present=True, body_present=True)
    tr.reset()
    assert tr.update(6.5, **FOCUSED_FRAME).verdict == FOCUSED
