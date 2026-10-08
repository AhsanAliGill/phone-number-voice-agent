"""Per-turn signal-to-noise estimate for the audio that reaches the STT.

The meter sits *after* noise suppression (it wraps ``Agent.stt_node``), so it
measures the residual noise the STT will actually hear. It needs no extra
model: frame levels are tracked in dBFS and

    noise floor = low percentile of all frame levels over a long window
    speech level = high percentile of frame levels during the current turn
    SNR          = speech level - noise floor

When suppression works, the floor is very low and the SNR is high. When noise
leaks through (loud chatter, clipping, a bad mic) the SNR drops and the
dialog re-asks for the segment instead of parsing a guess.
"""

from __future__ import annotations

from collections import deque

import numpy as np
from livekit import rtc

_MIN_DB = -90.0  # digital silence after suppression is clamped here


def frame_level_db(frame: rtc.AudioFrame) -> float:
    samples = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return _MIN_DB
    rms = float(np.sqrt(np.mean(samples * samples))) / 32768.0
    return max(_MIN_DB, 20.0 * np.log10(rms + 1e-12))


class SnrMeter:
    def __init__(
        self,
        *,
        noise_window_frames: int = 1500,  # ~15 s of 10 ms frames
        noise_percentile: float = 10.0,
        speech_percentile: float = 90.0,
        min_turn_frames: int = 10,
    ) -> None:
        self._history: deque[float] = deque(maxlen=noise_window_frames)
        self._turn: list[float] = []
        self._noise_pct = noise_percentile
        self._speech_pct = speech_percentile
        self._min_turn_frames = min_turn_frames

    def push(self, frame: rtc.AudioFrame) -> None:
        level = frame_level_db(frame)
        self._history.append(level)
        self._turn.append(level)

    def consume_turn_snr(self) -> float | None:
        """Return the SNR (dB) of audio since the last call, then reset."""
        turn, self._turn = self._turn, []
        if len(turn) < self._min_turn_frames or len(self._history) < self._min_turn_frames:
            return None
        noise_floor = float(np.percentile(self._history, self._noise_pct))
        speech_level = float(np.percentile(turn, self._speech_pct))
        return speech_level - noise_floor
