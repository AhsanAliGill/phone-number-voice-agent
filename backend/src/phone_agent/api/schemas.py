from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from ..parsing import validate_indian_mobile

Language = Literal["en", "hi", "mixed"]


class _CamelModel(BaseModel):
    """JSON uses camelCase (rawTranscript, parsedNumber, collectedAt)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class PhoneCreate(_CamelModel):
    raw_transcript: str = Field(min_length=1, max_length=5000)
    parsed_number: str
    language: Language
    collected_at: datetime | None = None

    @field_validator("parsed_number")
    @classmethod
    def _must_be_indian_mobile(cls, value: str) -> str:
        value = value.strip()
        if (error := validate_indian_mobile(value)) is not None:
            raise ValueError(
                f"parsedNumber must be exactly 10 digits starting with 6-9 ({error.value})"
            )
        return value

    @field_validator("collected_at")
    @classmethod
    def _assume_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class PhoneOut(_CamelModel):
    id: int
    raw_transcript: str
    parsed_number: str
    language: Language
    collected_at: datetime

    @field_validator("collected_at")
    @classmethod
    def _mark_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class PhoneStats(_CamelModel):
    total: int
    by_language: dict[Language, int]


class ParseRequest(_CamelModel):
    transcript: str


class ParseResponse(_CamelModel):
    digits: str
    digit_count: int
    language: Language
    corrected: bool
    is_valid: bool
    error: str | None


class TokenResponse(_CamelModel):
    server_url: str
    room_name: str
    participant_token: str
