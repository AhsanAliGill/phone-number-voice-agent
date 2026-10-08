"""TTS cache for prompts that never change (greeting, error prompts, ...).

Static prompts are synthesised once, kept in memory and written to disk as
WAV, so later calls and restarts play them instantly without a TTS request.
Dynamic sentences (the digit-by-digit confirmation) are streamed as usual.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import wave
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np
from livekit import rtc
from livekit.agents import APIStatusError
from livekit.agents import tts as lk_tts

logger = logging.getLogger("phone-agent.tts-cache")

_CHUNK_MS = 50  # split cached audio into small frames so it stays interruptible


class TTSCache:
    def __init__(self, tts: lk_tts.TTS, cache_dir: str | Path, namespace: str) -> None:
        self._tts = tts
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._namespace = namespace  # e.g. model + voice: changing either invalidates the cache
        self._memory: dict[str, rtc.AudioFrame] = {}
        self._lock = asyncio.Lock()

    def _path(self, text: str) -> Path:
        digest = hashlib.sha1(f"{self._namespace}|{text}".encode()).hexdigest()[:20]
        return self._dir / f"{digest}.wav"

    def get(self, text: str) -> rtc.AudioFrame | None:
        if (frame := self._memory.get(text)) is not None:
            return frame
        path = self._path(text)
        if path.exists():
            frame = _read_wav(path)
            self._memory[text] = frame
            return frame
        return None

    async def ensure(self, text: str) -> rtc.AudioFrame:
        if (frame := self.get(text)) is not None:
            return frame
        async with self._lock:
            if (frame := self.get(text)) is not None:
                return frame
            frames: list[rtc.AudioFrame] = []
            async with self._tts.synthesize(text) as stream:
                async for audio in stream:
                    frames.append(audio.frame)
            frame = rtc.combine_audio_frames(frames)
            _write_wav(self._path(text), frame)
            self._memory[text] = frame
            return frame

    async def prewarm(self, texts: list[str]) -> None:
        for text in texts:
            try:
                await self.ensure(text)
            except APIStatusError as e:
                if e.retryable:
                    logger.warning("failed to pre-synthesise prompt", extra={"text": text})
                    continue
                # a config problem (bad key, model terms not accepted...) affects
                # every prompt: report it once instead of once per prompt
                logger.error(
                    "TTS request rejected, skipping the prompt cache: %s (HTTP %s). "
                    "Check the TTS API key / model access.",
                    e.message,
                    e.status_code,
                )
                return
            except Exception:
                logger.exception("failed to pre-synthesise prompt", extra={"text": text})
        logger.info("tts cache ready", extra={"prompts": len(texts)})


async def iter_frames(frame: rtc.AudioFrame) -> AsyncIterator[rtc.AudioFrame]:
    samples = np.frombuffer(bytes(frame.data), dtype=np.int16)
    step = frame.sample_rate * _CHUNK_MS // 1000 * frame.num_channels
    for start in range(0, len(samples), step):
        chunk = samples[start : start + step]
        yield rtc.AudioFrame(
            data=chunk.tobytes(),
            sample_rate=frame.sample_rate,
            num_channels=frame.num_channels,
            samples_per_channel=len(chunk) // frame.num_channels,
        )


def _write_wav(path: Path, frame: rtc.AudioFrame) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(frame.num_channels)
        wav.setsampwidth(2)
        wav.setframerate(frame.sample_rate)
        wav.writeframes(bytes(frame.data))


def _read_wav(path: Path) -> rtc.AudioFrame:
    with wave.open(str(path), "rb") as wav:
        channels, rate = wav.getnchannels(), wav.getframerate()
        data = wav.readframes(wav.getnframes())
    return rtc.AudioFrame(
        data=data,
        sample_rate=rate,
        num_channels=channels,
        samples_per_channel=len(data) // (2 * channels),
    )
