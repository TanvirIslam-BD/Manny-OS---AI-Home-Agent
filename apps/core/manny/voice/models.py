"""Transport-neutral audio and transcript models."""

from __future__ import annotations

import io
import wave

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

    def to_wav(self) -> bytes:
        """Wrap the samples in a WAV container for transport to a browser.

        Adapters return bare signed 16-bit PCM because the speaker adapters accept
        it directly, but a browser needs a container it can decode. WAV costs a
        44-byte header and no codec dependency, which matters on a device that
        already budgets memory for a model.
        """
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(self.channels)
            output.setsampwidth(2)
            output.setframerate(self.sample_rate)
            output.writeframes(self.pcm)
        return buffer.getvalue()


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
    # Carried so a spoken turn can be announced the same way a typed one is.
    intent: str = "general"
    data: dict[str, object] | None = None
