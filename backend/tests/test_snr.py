import numpy as np
from livekit import rtc

from phone_agent.agent.snr import SnrMeter

RNG = np.random.default_rng(0)


def _frame(amplitude: float, ms: int = 50, rate: int = 24000) -> rtc.AudioFrame:
    n = rate * ms // 1000
    samples = RNG.normal(0, amplitude, n).clip(-32767, 32767).astype(np.int16)
    return rtc.AudioFrame(samples.tobytes(), rate, 1, n)


def _turn(meter: SnrMeter, silence_s: float, speech_s: float, noise: float, speech: float) -> float:
    for _ in range(int(silence_s * 20)):
        meter.push(_frame(noise))
    for _ in range(int(speech_s * 20)):
        meter.push(_frame(speech))
    return meter.consume_turn_snr()


def test_short_word_after_long_silence_is_not_flagged() -> None:
    # regression: "Hello?" after 12 s of silence used to report SNR = 0 dB
    snr = _turn(SnrMeter(), silence_s=12, speech_s=0.6, noise=20, speech=5000)
    assert snr > 30


def test_noisy_speech_is_flagged() -> None:
    snr = _turn(SnrMeter(), silence_s=5, speech_s=1.5, noise=3000, speech=4000)
    assert snr < 8


def test_too_little_audio_returns_none() -> None:
    meter = SnrMeter()
    meter.push(_frame(1000))
    assert meter.consume_turn_snr() is None
