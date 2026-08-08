"""Deterministic local voice fixtures used by simulator and CI."""

from manny.i18n import detect_text_language
from manny.voice.models import AudioBuffer, Transcript


class MockWakeWord:
    async def detected(self, audio: AudioBuffer) -> bool:
        return b"hey manny" in audio.pcm.lower()


class MockVoiceActivity:
    async def contains_speech(self, audio: AudioBuffer) -> bool:
        return bool(audio.pcm.strip())


class MockSpeechToText:
    async def transcribe(self, audio: AudioBuffer) -> Transcript:
        text = audio.pcm.decode("utf-8", errors="replace").strip()
        return Transcript(
            text=text,
            language=detect_text_language(text, audio.language_hint),
        )


class MockTextToSpeech:
    async def synthesize(self, text: str, voice: str, language: str) -> AudioBuffer:
        del voice
        return AudioBuffer(pcm=text.encode("utf-8"), language_hint=language)
