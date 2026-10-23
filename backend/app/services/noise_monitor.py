"""
Background-noise monitor — loudness only, no audio model and no audio I/O.

The browser measures RMS loudness (dBFS) on-device and sends just that number
on the session heartbeat. This class decides whether the room has become
*sustainedly* loud relative to the level measured at session start:

- The first ``baseline_samples`` usable samples form a median baseline.
- A sample is "loud" when it is at least ``loud_delta_db`` above baseline.
- ``sustain_beats`` loud samples in a row are required, so a cough, a door or
  a dropped book never fires.
- If the baseline itself is already very loud, the session starts in a noisy
  room: fire once, right after calibration, instead of waiting for a rise.
- Samples taken while lesson audio is playing are ignored entirely, because
  the speakers feed the lesson back into the microphone.

One-time semantics: a detection stays pending (``update`` keeps returning
True) until the caller confirms the notice was actually shown via
``mark_notice_shown()`` — so a detection blocked by a pending visual
intervention is not lost. After that, this monitor never fires again for
the rest of the session.
"""
from __future__ import annotations

import statistics
from typing import Optional

BASELINE_SAMPLES = 5
LOUD_DELTA_DB = 12.0
SUSTAIN_BEATS = 4
ALREADY_LOUD_DBFS = -20.0


class NoiseMonitor:
    """Per-session background-noise state. Pure logic, unit-test friendly."""

    def __init__(
        self,
        baseline_samples: int = BASELINE_SAMPLES,
        loud_delta_db: float = LOUD_DELTA_DB,
        sustain_beats: int = SUSTAIN_BEATS,
        already_loud_dbfs: float = ALREADY_LOUD_DBFS,
    ):
        self.baseline_samples = int(baseline_samples)
        self.loud_delta_db = float(loud_delta_db)
        self.sustain_beats = int(sustain_beats)
        self.already_loud_dbfs = float(already_loud_dbfs)

        self._baseline_samples: list[float] = []
        self.baseline_dbfs: Optional[float] = None
        self.loud_streak: int = 0
        self._detection_pending: bool = False
        self._notice_shown: bool = False

    @property
    def is_calibrated(self) -> bool:
        return self.baseline_dbfs is not None

    @property
    def notice_shown(self) -> bool:
        return self._notice_shown

    def mark_notice_shown(self) -> None:
        """Latch the one-per-session notice as shown; never fire again."""
        self._notice_shown = True
        self._detection_pending = False
        self.loud_streak = 0

    def update(
        self,
        noise_dbfs: Optional[float],
        lesson_audio_active: bool = False,
    ) -> bool:
        """
        Feed one heartbeat sample. Returns True when a noise cue should fire.

        ``None`` (no mic / metering unavailable) and lesson-audio samples are
        skipped: they neither calibrate the baseline nor move the streak.
        """
        if lesson_audio_active or noise_dbfs is None:
            return False

        # Once-per-session: after the notice has been shown, never again.
        if self._notice_shown:
            return False

        # A detection the caller could not yet show (e.g. a visual
        # intervention was pending) stays pending rather than being lost.
        if self._detection_pending:
            return True

        level = max(-100.0, min(0.0, float(noise_dbfs)))

        if self.baseline_dbfs is None:
            self._baseline_samples.append(level)
            if len(self._baseline_samples) < self.baseline_samples:
                return False
            self.baseline_dbfs = float(statistics.median(self._baseline_samples))
            self._baseline_samples = []
            if self.baseline_dbfs >= self.already_loud_dbfs:
                self._detection_pending = True
                return True
            return False

        if level >= self.baseline_dbfs + self.loud_delta_db:
            self.loud_streak += 1
        else:
            self.loud_streak = 0

        if self.loud_streak >= self.sustain_beats:
            self.loud_streak = 0
            self._detection_pending = True
            return True
        return False
