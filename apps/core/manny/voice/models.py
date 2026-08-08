"""Transport-neutral audio and transcript models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from manny.i18n import LANGUAGE_TAG_PATTERN


class AudioBuffer(BaseModel):
    model_config = ConfigDict(frozen=True)

    pcm: bytes
    sample_rate: int = Field(default=16_000, ge=8_000, le=48_000)
    channels: int = Field(default=1, ge=1, le=2)
    language_hint: str | None = Field(
        default=None,
        min_length=2,
        max_length=35,
        pattern=rf"^(?:auto|{LANGUAGE_TAG_PATTERN.pattern[1:-1]})$",
    )


class Transcript(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    confidence: float = Field(default=1.0, ge=0, le=1)
    is_final: bool = True
    language: str = Field(default="en", min_length=2, max_length=35)


class VoiceTurnResult(BaseModel):
    transcript: Transcript
    answer: str
    audio: AudioBuffer
    tool_name: str | None = None
    language: str = "en"
