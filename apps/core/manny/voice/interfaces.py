"""Voice backends remain replaceable and locally hosted."""

from __future__ import annotations

from typing import Protocol

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


class AudioPlayback(Protocol):
    async def play(self, audio: AudioBuffer) -> None: ...
