"""Per-turn signal-to-noise estimate for the audio that reaches the STT.

The meter sits *after* noise suppression (it wraps ``Agent.stt_node``), so it
measures the residual noise the STT will actually hear. It needs no extra
model: frame levels are tracked in dBFS and

    noise floor  = low percentile of all frame levels over a long window
    speech level = mean of the loudest ~300 ms of the current turn
    SNR          = speech level - noise floor

The speech level deliberately does not use a percentile of the whole turn:
a turn's buffer includes the silence before the user spoke (often >90 % of
the frames after a long pause), which would drag a percentile down to the
noise floor and report SNR = 0 for perfectly clean speech.

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
        noise_window_s: float = 15.0,
        noise_percentile: float = 10.0,
        speech_window_s: float = 0.3,
        min_turn_s: float = 0.2,
    ) -> None:
        self._noise_window_s = noise_window_s
        self._history: deque[float] = deque()
        self._turn: list[float] = []
        self._frame_s = 0.01  # updated from the frames we actually receive
        self._noise_pct = noise_percentile
        self._speech_window_s = speech_window_s
        self._min_turn_s = min_turn_s

    def push(self, frame: rtc.AudioFrame) -> None:
        if frame.sample_rate:
            self._frame_s = frame.samples_per_channel / frame.sample_rate
        level = frame_level_db(frame)
        self._history.append(level)
        while len(self._history) * self._frame_s > self._noise_window_s:
            self._history.popleft()
        self._turn.append(level)

    def consume_turn_snr(self) -> float | None:
        """Return the SNR (dB) of audio since the last call, then reset."""
        turn, self._turn = self._turn, []
        min_frames = max(1, round(self._min_turn_s / self._frame_s))
        if len(turn) < min_frames or len(self._history) < min_frames:
            return None
        noise_floor = float(np.percentile(self._history, self._noise_pct))
        loudest = max(1, round(self._speech_window_s / self._frame_s))
        speech_level = float(np.mean(np.sort(turn)[-loudest:]))
        return speech_level - noise_floor
