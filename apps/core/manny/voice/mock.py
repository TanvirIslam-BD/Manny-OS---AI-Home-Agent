"""Deterministic local voice fixtures used by simulator and CI."""

from manny.voice.models import AudioBuffer, Transcript


class MockWakeWord:
    async def detected(self, audio: AudioBuffer) -> bool:
        return b"hey manny" in audio.pcm.lower()


class MockVoiceActivity:
    async def contains_speech(self, audio: AudioBuffer) -> bool:
        return bool(audio.pcm.strip())


class MockSpeechToText:
    async def transcribe(self, audio: AudioBuffer) -> Transcript:
        return Transcript(text=audio.pcm.decode("utf-8", errors="replace").strip())


class MockTextToSpeech:
    async def synthesize(self, text: str, voice: str) -> AudioBuffer:
        del voice
        return AudioBuffer(pcm=text.encode("utf-8"))
