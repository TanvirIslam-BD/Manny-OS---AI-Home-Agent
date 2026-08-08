"""Transport-neutral audio and transcript models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AudioBuffer(BaseModel):
    model_config = ConfigDict(frozen=True)

    pcm: bytes
    sample_rate: int = Field(default=16_000, ge=8_000, le=48_000)
    channels: int = Field(default=1, ge=1, le=2)


class Transcript(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    confidence: float = Field(default=1.0, ge=0, le=1)
    is_final: bool = True


class VoiceTurnResult(BaseModel):
    transcript: Transcript
    answer: str
    audio: AudioBuffer
    tool_name: str | None = None
