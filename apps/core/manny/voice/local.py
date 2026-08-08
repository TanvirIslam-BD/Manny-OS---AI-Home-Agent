"""Optional fully local Moonshine and Kokoro adapters."""

from __future__ import annotations

import asyncio
import importlib
import os
import tempfile
import wave
from array import array
from pathlib import Path
from typing import Any

from manny.voice.models import AudioBuffer, Transcript


class MoonshineSpeechToText:
    """File-based Moonshine ONNX adapter; temporary audio is always removed."""

    def __init__(self, model: str = "moonshine/tiny") -> None:
        self._model = model

    async def transcribe(self, audio: AudioBuffer) -> Transcript:
        return await asyncio.to_thread(self._transcribe_sync, audio)

    def _transcribe_sync(self, audio: AudioBuffer) -> Transcript:
        try:
            moonshine = importlib.import_module("moonshine_onnx")
        except ImportError as exc:
            raise RuntimeError("install the validated Moonshine ONNX runtime") from exc
        descriptor, raw_path = tempfile.mkstemp(prefix="manny-stt-", suffix=".wav")
        os.close(descriptor)
        path = Path(raw_path)
        try:
            with wave.open(str(path), "wb") as output:
                output.setnchannels(audio.channels)
                output.setsampwidth(2)
                output.setframerate(audio.sample_rate)
                output.writeframes(audio.pcm)
            lines = moonshine.transcribe(path, self._model)
            return Transcript(text=" ".join(str(line) for line in lines).strip())
        finally:
            path.unlink(missing_ok=True)


class KokoroTextToSpeech:
    """Kokoro KPipeline adapter producing mono signed 16-bit PCM."""

    def __init__(self, language: str = "a") -> None:
        self._language = language
        self._pipeline: Any = None

    async def synthesize(self, text: str, voice: str) -> AudioBuffer:
        return await asyncio.to_thread(self._synthesize_sync, text, voice)

    def _synthesize_sync(self, text: str, voice: str) -> AudioBuffer:
        if self._pipeline is None:
            try:
                kokoro = importlib.import_module("kokoro")
            except ImportError as exc:
                raise RuntimeError("install the validated Kokoro runtime") from exc
            self._pipeline = kokoro.KPipeline(lang_code=self._language)
        samples = array("h")
        for _graphemes, _phonemes, audio in self._pipeline(text, voice=voice):
            values = audio.tolist() if hasattr(audio, "tolist") else audio
            samples.extend(round(max(-1.0, min(1.0, float(value))) * 32767) for value in values)
        return AudioBuffer(pcm=samples.tobytes(), sample_rate=24_000)
