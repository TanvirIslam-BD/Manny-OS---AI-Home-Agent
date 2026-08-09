"""Voice backends remain replaceable and locally hosted."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from manny.voice.models import AudioBuffer, Transcript


class WakeWordDetector(Protocol):
    async def detected(self, audio: AudioBuffer) -> bool: ...


class VoiceActivityDetector(Protocol):
    async def contains_speech(self, audio: AudioBuffer) -> bool: ...


class SpeechToText(Protocol):
    async def transcribe(self, audio: AudioBuffer) -> Transcript: ...


class TextToSpeech(Protocol):
    async def synthesize(self, text: str, voice: str, language: str) -> AudioBuffer: ...


class AudioCapture(Protocol):
    async def is_muted(self) -> bool: ...
    async def capture(self, seconds: float) -> AudioBuffer: ...


@runtime_checkable
class AudioFrameSource(Protocol):
    """A recorder that can be read continuously in small frames.

    Fixed-length capture cannot end an utterance at the right moment: it stops on a
    clock rather than on the speaker, so a question longer than the window is cut in
    half and a short one still costs the full window. Reading frames as they arrive
    lets voice activity decide where speech ends.

    Separate from `AudioCapture` because not every recorder can do it — the mocks
    and the desktop simulator do not — so the listen loop treats it as optional.
    """

    def stream(self, frame_seconds: float) -> AsyncIterator[AudioBuffer]: ...


class AudioPlayback(Protocol):
    async def play(self, audio: AudioBuffer) -> None: ...
