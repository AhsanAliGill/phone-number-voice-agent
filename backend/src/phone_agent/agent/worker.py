"""LiveKit voice agent that collects a 10-digit Indian mobile number.

Pipeline (no LLM anywhere — every decision is deterministic):

    mic -> noise suppression (LiveKit BVC) -> Silero VAD -> SNR meter
        -> Deepgram Nova-3 "multi" streaming (or Groq Whisper large-v3-turbo)
        -> PhoneCollector state machine -> Deepgram Aura-2 TTS (+ cache)

Run:
    uv run phone-agent download-files   # once: VAD / noise model weights
    uv run phone-agent dev              # connect to LIVEKIT_URL
    uv run phone-agent console          # talk to it from the terminal
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterable

import httpx
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    ModelSettings,
    StopResponse,
    cli,
    llm,
    room_io,
    stt,
)
from livekit.agents.voice.events import UserStateChangedEvent
from livekit.plugins import deepgram, groq, noise_cancellation, silero

from ..config import Settings, get_settings
from ..dialog import CollectedNumber, PhoneCollector, Reply, TurnQuality, static_prompts
from ..dialog.prompts import render
from .snr import SnrMeter
from .tts_cache import TTSCache, iter_frames

load_dotenv()
logger = logging.getLogger("phone-agent")


class PhoneAgent(Agent):
    def __init__(self, settings: Settings, tts_cache: TTSCache) -> None:
        super().__init__(
            instructions="Collect the caller's 10-digit mobile number. Replies are deterministic."
        )
        self._settings = settings
        self._cache = tts_cache
        self._collector = PhoneCollector(
            # Whisper returns no confidence score, so only the SNR gate applies
            min_stt_confidence=(
                settings.min_stt_confidence if settings.stt_provider == "deepgram" else 0.0
            ),
            min_snr_db=settings.min_snr_db,
            hindi_prompts=False,  # Groq / Deepgram TTS voices are English-only
        )
        self._snr = SnrMeter()
        self._stt_language: str | None = None
        self._pause_task: asyncio.Task[None] | None = None
        self._last_speech_end = time.monotonic()

    # ------------------------------------------------------------ lifecycle
    async def on_enter(self) -> None:
        self.session.on("user_state_changed", self._on_user_state_changed)
        await self._execute(self._collector.greeting())

    def _on_user_state_changed(self, ev: UserStateChangedEvent) -> None:
        if ev.new_state == "speaking":
            # the user resumed — never interrupt a number that is still coming
            self._cancel_pause_timer()
        elif ev.old_state == "speaking":
            self._last_speech_end = time.monotonic()

    # ------------------------------------------------------------ STT node
    async def stt_node(
        self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings
    ) -> AsyncIterable[stt.SpeechEvent]:
        """Meter the (noise-suppressed) audio on its way to the STT."""

        async def metered() -> AsyncIterable[rtc.AudioFrame]:
            async for frame in audio:
                self._snr.push(frame)
                yield frame

        async for event in Agent.default.stt_node(self, metered(), model_settings):
            if event.type == stt.SpeechEventType.FINAL_TRANSCRIPT and event.alternatives:
                self._stt_language = event.alternatives[0].language or self._stt_language
            yield event

    # ------------------------------------------------------------ turns
    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        self._cancel_pause_timer()
        transcript = new_message.text_content or ""
        quality = TurnQuality(
            stt_confidence=new_message.transcript_confidence,
            snr_db=self._snr.consume_turn_snr(),
            stt_language=self._stt_language,
        )
        reply = self._collector.on_user_turn(transcript, quality)
        logger.info(
            "user turn",
            extra={
                "transcript": transcript,
                "confidence": quality.stt_confidence,
                "snr_db": quality.snr_db,
                "state": self._collector.state.value,
                "digits_so_far": self._collector.digits_so_far,
                "reply": reply.text,
            },
        )
        await self._execute(reply)
        raise StopResponse()  # replies come only from the state machine

    # ------------------------------------------------------------ pause timer
    def _start_pause_timer(self) -> None:
        self._cancel_pause_timer()
        self._pause_task = asyncio.create_task(self._pause_timer())

    def _cancel_pause_timer(self) -> None:
        if self._pause_task is not None and not self._pause_task.done():
            self._pause_task.cancel()
        self._pause_task = None

    async def _pause_timer(self) -> None:
        """Wait silently until the user has been quiet for ``pause_timeout_s``."""
        remaining = self._settings.pause_timeout_s - (time.monotonic() - self._last_speech_end)
        if remaining > 0:
            await asyncio.sleep(remaining)
        if self.session.user_state == "speaking":
            return
        self._pause_task = None  # we are about to reply; don't cancel ourselves
        await self._execute(self._collector.on_silence_timeout())

    # ------------------------------------------------------------ actions
    async def _execute(self, reply: Reply) -> None:
        text = reply.text
        cacheable = reply.cacheable
        if reply.save is not None and not await self._save(reply.save):
            text = render("save_failed", self._collector.prompt_lang)
            cacheable = True

        handle = self._speak(text, cacheable) if text else None

        if reply.wait_for_more:
            self._start_pause_timer()

        if reply.end_call:

            async def hang_up() -> None:
                if handle is not None:
                    await handle.wait_for_playout()
                self.session.shutdown()

            asyncio.create_task(hang_up())

    def _speak(self, text: str, cacheable: bool):
        cached = self._cache.get(text) if cacheable else None
        if cached is not None:
            return self.session.say(text, audio=iter_frames(cached))
        return self.session.say(text)

    async def _save(self, number: CollectedNumber) -> bool:
        payload = {
            "rawTranscript": number.raw_transcript,
            "parsedNumber": number.parsed_number,
            "language": number.language,
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(f"{self._settings.api_base_url}/api/phone", json=payload)
                resp.raise_for_status()
        except httpx.HTTPError:
            logger.exception("failed to save phone number", extra=payload)
            return False
        logger.info("phone number saved", extra=resp.json())
        return True


# ---------------------------------------------------------------- server
def _noise_cancellation(mode: str):
    return {
        "bvc": noise_cancellation.BVC,
        "bvc_telephony": noise_cancellation.BVCTelephony,
        "nc": noise_cancellation.NC,
    }.get(mode, lambda: None)()


def _make_stt(settings: Settings) -> stt.STT:
    if settings.stt_provider == "groq":
        # Whisper is not streaming: Agent.default.stt_node wraps it with the
        # session's Silero VAD so each utterance is sent once speech ends.
        return groq.STT(
            model=settings.groq_stt_model,
            language=settings.groq_stt_language,
            detect_language=not settings.groq_stt_language,
            prompt=settings.groq_stt_prompt,
            **({"api_key": settings.groq_api_key} if settings.groq_api_key else {}),
        )
    return deepgram.STT(
        model=settings.deepgram_model,
        language=settings.deepgram_language,
        interim_results=True,
        punctuate=True,
        api_key=settings.deepgram_api_key or None,
    )


def _make_tts(settings: Settings):
    """Return the TTS engine and a voice id used to namespace the TTS cache."""
    if settings.tts_provider == "groq":
        tts = groq.TTS(
            model=settings.groq_tts_model,
            voice=settings.groq_tts_voice,
            **({"api_key": settings.groq_api_key} if settings.groq_api_key else {}),
        )
        return tts, f"groq:{settings.groq_tts_model}:{settings.groq_tts_voice}"
    tts = deepgram.TTS(
        model=settings.deepgram_tts_model, api_key=settings.deepgram_api_key or None
    )
    return tts, f"deepgram:{settings.deepgram_tts_model}"


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


server = AgentServer(setup_fnc=prewarm)


@server.rtc_session(agent_name=get_settings().agent_name)
async def entrypoint(ctx: JobContext) -> None:
    settings = get_settings()

    tts, voice = _make_tts(settings)
    tts_cache = TTSCache(tts, settings.tts_cache_dir, namespace=voice)
    # greeting first so the opening line is ready; the rest warms in background
    await tts_cache.prewarm([render("greeting", "en")])
    # only English prompts: the Groq / Deepgram voices can't speak Hindi
    prewarm_task = asyncio.create_task(tts_cache.prewarm(static_prompts(("en",))))

    session = AgentSession(
        stt=_make_stt(settings),
        tts=tts,
        vad=ctx.proc.userdata["vad"],
        turn_handling={
            "turn_detection": "vad",
            "endpointing": {"min_delay": settings.endpointing_min_delay_s},
            "preemptive_generation": {"enabled": False},
        },
    )

    await session.start(
        agent=PhoneAgent(settings, tts_cache),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=_noise_cancellation(settings.noise_cancellation)
            ),
        ),
    )
    ctx.add_shutdown_callback(lambda: _cancel(prewarm_task))


async def _cancel(task: asyncio.Task[None]) -> None:
    task.cancel()


def main() -> None:
    cli.run_app(server)


if __name__ == "__main__":
    main()
