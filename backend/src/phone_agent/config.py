from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LiveKit -----------------------------------------------------------
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    # empty = automatic dispatch into every new room; set a name for explicit dispatch
    agent_name: str = ""

    # --- STT --------------------------------------------------------------
    # deepgram = Nova-3 streaming with interim results + confidence (default)
    # groq = Whisper via the Groq API (per-utterance, segmented by Silero VAD)
    stt_provider: Literal["deepgram", "groq"] = "deepgram"
    groq_stt_model: str = "whisper-large-v3-turbo"
    # empty = let Whisper detect the language of each utterance (needed for Hinglish)
    groq_stt_language: str = ""
    # describes the audio without containing digits: digits in a Whisper prompt
    # can be "hallucinated" back on silent or noisy segments
    groq_stt_prompt: str = (
        "A caller says their Indian mobile phone number in English, Hindi or Hinglish."
    )
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"
    # "multi" = Nova-3 multilingual code-switching (English + Hindi in one stream)
    deepgram_language: str = "multi"

    # --- TTS --------------------------------------------------------------
    # groq_api_key is shared by Groq STT and TTS. Both providers have English voices only, so the agent replies in English
    # (it still understands Hindi / Hinglish).
    # deepgram = Aura-2 (same key as STT, default), groq = Orpheus via the Groq API
    tts_provider: Literal["deepgram", "groq"] = "deepgram"
    groq_api_key: str = ""
    groq_tts_model: str = "canopylabs/orpheus-v1-english"
    groq_tts_voice: str = "autumn"
    deepgram_tts_model: str = "aura-2-andromeda-en"
    tts_cache_dir: str = ".cache/tts"

    # --- Audio quality -----------------------------------------------------
    # bvc = LiveKit Cloud background voice cancellation (Krisp-based)
    noise_cancellation: Literal["bvc", "bvc_telephony", "nc", "none"] = "bvc"
    min_snr_db: float = 8.0
    min_stt_confidence: float = 0.55

    # --- Turn taking -------------------------------------------------------
    pause_timeout_s: float = 4.0
    endpointing_min_delay_s: float = 0.6

    # --- Backend -----------------------------------------------------------
    database_url: str = "sqlite:///./data/phone_numbers.db"
    api_base_url: str = "http://127.0.0.1:8000"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: list[str] = ["*"]
    # served at "/" when present; empty = ../frontend next to this backend folder
    frontend_dir: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
