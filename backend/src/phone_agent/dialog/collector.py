"""Conversation state machine for collecting a phone number.

This module knows nothing about LiveKit. The voice agent feeds it user turns
and silence timeouts and executes the ``Reply`` it gets back, which keeps the
whole flow deterministic and unit-testable.

    COLLECTING --10 valid digits--> CONFIRMING --yes--> DONE
        ^  |                            |
        |  +--<10 digits: stay silent,  +--no / new number--> COLLECTING
        |     wait for more (4 s)
        +---- too many / invalid / timeout: reset and re-ask
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..parsing import (
    ParseError,
    ParseResult,
    classify_confirmation,
    is_lead_in,
    parse_phone_number,
)
from ..parsing.phone_parser import Language
from .prompts import PromptLang, is_static, render, spell_digits


class State(str, Enum):
    COLLECTING = "collecting"
    CONFIRMING = "confirming"
    DONE = "done"


@dataclass(frozen=True)
class CollectedNumber:
    raw_transcript: str
    parsed_number: str
    language: Language


@dataclass(frozen=True)
class Reply:
    text: str | None = None
    """What to say. ``None`` means stay silent."""
    cacheable: bool = False
    """True when ``text`` is a static prompt that can be served from the TTS cache."""
    wait_for_more: bool = False
    """Start the pause timer: the user is mid-number and may keep talking."""
    save: CollectedNumber | None = None
    """Persist this number (the user just confirmed it)."""
    end_call: bool = False


SILENT_WAIT = Reply(wait_for_more=True)


@dataclass
class TurnQuality:
    """Signal quality of one user turn, measured by the voice pipeline."""

    stt_confidence: float | None = None
    snr_db: float | None = None
    stt_language: str | None = None
    """Language reported by the STT, used to tag numeral-only transcripts."""


@dataclass
class PhoneCollector:
    min_stt_confidence: float = 0.55
    min_snr_db: float = 8.0
    hindi_prompts: bool = True
    """Reply in Hindi to Hindi speakers. Off when the TTS voice is English-only."""

    state: State = State.COLLECTING
    segments: list[str] = field(default_factory=list)
    """Transcripts of the current attempt — together they form the number."""
    candidate: ParseResult | None = None
    prompt_lang: PromptLang = "en"
    fallback_language: Language = "en"

    # ------------------------------------------------------------------ helpers
    def _say(self, key: str, **kwargs: object) -> Reply:
        return Reply(text=render(key, self.prompt_lang, **kwargs), cacheable=is_static(key))

    def _reset(self) -> None:
        self.state = State.COLLECTING
        self.segments.clear()
        self.candidate = None

    def _current(self) -> ParseResult:
        return parse_phone_number(
            " ".join(self.segments), fallback_language=self.fallback_language
        )

    def _is_low_quality(self, quality: TurnQuality | None) -> bool:
        if quality is None:
            return False
        if quality.snr_db is not None and quality.snr_db < self.min_snr_db:
            return True
        if quality.stt_confidence is not None and quality.stt_confidence < self.min_stt_confidence:
            return True
        return False

    def _update_prompt_lang(self, result: ParseResult) -> None:
        # Answer in Hindi only when the user spoke pure Hindi; English or
        # Hinglish speakers get English prompts.
        if result.language == "hi" and self.hindi_prompts:
            self.prompt_lang = "hi"
        elif result.language == "en":
            self.prompt_lang = "en"

    # --------------------------------------------------------------- public API
    @property
    def digits_so_far(self) -> str:
        return self._current().digits

    def greeting(self) -> Reply:
        return self._say("greeting")

    def on_user_turn(self, transcript: str, quality: TurnQuality | None = None) -> Reply:
        transcript = transcript.strip()
        if not transcript or self.state is State.DONE:
            return Reply()
        if self.state is State.CONFIRMING:
            return self._on_confirmation_turn(transcript)
        return self._on_collecting_turn(transcript, quality)

    def on_silence_timeout(self) -> Reply:
        """The user went quiet for the full pause window with <10 digits."""
        if self.state is not State.COLLECTING:
            return Reply()
        count = self._current().digit_count
        if count == 0:
            # "my number is…" and then nothing: ask for the number once
            if self.segments:
                self.segments.clear()
                return self._say("ask_number")
            return Reply()
        self._reset()
        return self._say("too_few", count=count)

    # ------------------------------------------------------------------ states
    def _on_collecting_turn(self, transcript: str, quality: TurnQuality | None) -> Reply:
        if self._is_low_quality(quality):
            # Don't feed noisy audio to the parser: discard only this segment
            # and re-ask for it, keeping digits already collected.
            if self._current().digit_count > 0:
                return self._say("unclear_segment")
            return self._say("unclear_number")

        if quality is not None and quality.stt_language:
            self.fallback_language = "hi" if quality.stt_language.startswith("hi") else "en"

        self.segments.append(transcript)
        result = self._current()
        self._update_prompt_lang(result)

        if result.error is ParseError.NO_DIGITS:
            if result.corrected:
                return SILENT_WAIT  # "wait, sorry..." — user is about to restart
            if is_lead_in(transcript):
                return SILENT_WAIT  # "my number is…" — the digits come next
            self.segments.clear()
            return self._say("ask_number")

        if result.error is ParseError.TOO_FEW:
            # Never treat a pause as end-of-number while we have < 10 digits.
            return SILENT_WAIT

        if result.error is ParseError.TOO_MANY:
            self._reset()
            return self._say("too_many", count=result.digit_count)

        if result.error is ParseError.INVALID_PREFIX:
            self._reset()
            return self._say("invalid")

        self.state = State.CONFIRMING
        self.candidate = result
        return self._say("confirm", spoken=spell_digits(result.digits, self.prompt_lang))

    def _on_confirmation_turn(self, transcript: str) -> Reply:
        assert self.candidate is not None
        answer = classify_confirmation(transcript)
        spoken_digits = parse_phone_number(transcript)

        if answer == "yes":
            collected = CollectedNumber(
                raw_transcript=" ".join(self.segments),
                parsed_number=self.candidate.digits,
                language=self.candidate.language,
            )
            self.state = State.DONE
            return Reply(
                text=render("saved", self.prompt_lang),
                cacheable=True,
                save=collected,
                end_call=True,
            )

        if spoken_digits.digit_count >= 3:
            # "No, it's 98765..." — treat the digits as a fresh attempt. The
            # threshold keeps "oh no" ("oh" = 0) from being read as a number.
            self._reset()
            return self._on_collecting_turn(transcript, None)

        if answer == "no":
            self._reset()
            return self._say("ask_again")

        return self._say(
            "confirm_yes_no", spoken=spell_digits(self.candidate.digits, self.prompt_lang)
        )
