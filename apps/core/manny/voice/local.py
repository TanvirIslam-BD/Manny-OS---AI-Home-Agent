"""Optional fully local Moonshine and Kokoro adapters."""

from __future__ import annotations

import asyncio
import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
import wave
from array import array
from math import sqrt
from pathlib import Path
from typing import Any

from manny.i18n import base_language, normalize_language_tag
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
    """Kokoro KPipeline adapter producing mono signed 16-bit PCM.

    Kokoro selects a speaker by its own voice identifier, not by an arbitrary name.
    The coordinator used to pass "manny", which eSpeak ignores and Kokoro cannot
    resolve, so this backend could not work as it was wired. The identifier now
    comes from MANNY_TTS_VOICE and the absence of one is reported here rather than
    surfacing as a failure inside the library.
    """

    def __init__(self, language: str = "a") -> None:
        self._language = language
        self._pipelines: dict[str, Any] = {}

    async def synthesize(self, text: str, voice: str, language: str = "en") -> AudioBuffer:
        if not voice:
            raise RuntimeError(
                "Kokoro needs a voice identifier from its own catalogue; set "
                "MANNY_TTS_VOICE to one the installed version publishes"
            )
        return await asyncio.to_thread(self._synthesize_sync, text, voice, language)

    def _synthesize_sync(self, text: str, voice: str, language: str) -> AudioBuffer:
        language_code = _kokoro_language(language, self._language)
        pipeline = self._pipelines.get(language_code)
        if pipeline is None:
            try:
                kokoro = importlib.import_module("kokoro")
            except ImportError as exc:
                raise RuntimeError("install the validated Kokoro runtime") from exc
            pipeline = kokoro.KPipeline(lang_code=language_code)
            self._pipelines[language_code] = pipeline
        samples = array("h")
        for _graphemes, _phonemes, audio in pipeline(text, voice=voice):
            values = audio.tolist() if hasattr(audio, "tolist") else audio
            samples.extend(round(max(-1.0, min(1.0, float(value))) * 32767) for value in values)
        return AudioBuffer(
            pcm=samples.tobytes(), sample_rate=24_000, language_hint=language
        )


class EnergyVoiceActivity:
    """RMS-threshold speech detection over signed 16-bit little-endian PCM.

    Deterministic and dependency-free, so it behaves identically in CI and on
    device. It gates recording, not recognition: a wake word can be layered in
    front of it through `WakeWordDetector` without changing this contract.
    """

    def __init__(self, *, threshold: float = 0.02, minimum_seconds: float = 0.2) -> None:
        self._threshold = threshold
        self._minimum_seconds = minimum_seconds

    async def contains_speech(self, audio: AudioBuffer) -> bool:
        return await asyncio.to_thread(self._contains_speech_sync, audio)

    def _contains_speech_sync(self, audio: AudioBuffer) -> bool:
        sample_count = len(audio.pcm) // 2
        if sample_count == 0:
            return False
        duration = sample_count / float(audio.sample_rate * audio.channels)
        if duration < self._minimum_seconds:
            return False
        samples = array("h")
        samples.frombytes(audio.pcm[: sample_count * 2])
        if sys.byteorder != "little":
            samples.byteswap()
        mean_square = sum(value * value for value in samples) / len(samples)
        return sqrt(mean_square) / 32_768 >= self._threshold


class WhisperCppSpeechToText:
    """Multilingual whisper.cpp CLI adapter with automatic language detection."""

    def __init__(
        self,
        *,
        binary: Path,
        model: Path,
        threads: int = 4,
        timeout_seconds: float = 90,
        default_language: str = "auto",
    ) -> None:
        self._binary = binary
        self._model = model
        self._threads = threads
        self._timeout = timeout_seconds
        self._default_language = default_language

    async def transcribe(self, audio: AudioBuffer) -> Transcript:
        return await asyncio.to_thread(self._transcribe_sync, audio)

    def _transcribe_sync(self, audio: AudioBuffer) -> Transcript:
        with tempfile.TemporaryDirectory(prefix="manny-whisper-") as raw_directory:
            directory = Path(raw_directory)
            audio_path = directory / "speech.wav"
            output_base = directory / "result"
            with wave.open(str(audio_path), "wb") as output:
                output.setnchannels(audio.channels)
                output.setsampwidth(2)
                output.setframerate(audio.sample_rate)
                output.writeframes(audio.pcm)
            command = [
                str(self._binary),
                "-m",
                str(self._model),
                "-f",
                str(audio_path),
                "-l",
                _whisper_language(audio.language_hint, self._default_language),
                "-t",
                str(self._threads),
                "-oj",
                "-of",
                str(output_base),
                "-np",
                "-nt",
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    check=False,
                    timeout=self._timeout,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError("local multilingual speech recognition failed") from exc
            output_path = output_base.with_suffix(".json")
            if result.returncode != 0 or not output_path.exists():
                raise RuntimeError("local multilingual speech recognition failed")
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
                segments = payload["transcription"]
                language = payload["result"]["language"]
                text = "".join(
                    str(segment["text"])
                    for segment in segments
                    if isinstance(segment, dict) and "text" in segment
                ).strip()
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise RuntimeError("whisper.cpp returned invalid transcription data") from exc
            if not text:
                raise RuntimeError("whisper.cpp returned an empty transcription")
            return Transcript(text=text, language=normalize_language_tag(str(language)))


class EspeakTextToSpeech:
    """Broad multilingual eSpeak NG CLI adapter returning transport-neutral PCM."""

    def __init__(self, binary: Path, *, timeout_seconds: float = 30) -> None:
        self._binary = binary
        self._timeout = timeout_seconds

    async def synthesize(self, text: str, voice: str, language: str = "en") -> AudioBuffer:
        del voice
        return await asyncio.to_thread(self._synthesize_sync, text, language)

    def _synthesize_sync(self, text: str, language: str) -> AudioBuffer:
        voice_code = _espeak_language(language)
        command = [str(self._binary), "--stdout", "--stdin", "-v", voice_code]
        try:
            result = subprocess.run(
                command,
                input=text.encode("utf-8"),
                capture_output=True,
                check=False,
                timeout=self._timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("local multilingual speech synthesis failed") from exc
        if result.returncode != 0 or not result.stdout:
            raise RuntimeError("local multilingual speech synthesis failed")
        try:
            with wave.open(io.BytesIO(result.stdout), "rb") as source:
                if source.getsampwidth() != 2:
                    raise RuntimeError("eSpeak NG returned unsupported audio")
                return AudioBuffer(
                    pcm=source.readframes(source.getnframes()),
                    sample_rate=source.getframerate(),
                    channels=source.getnchannels(),
                    language_hint=normalize_language_tag(language),
                )
        except (EOFError, wave.Error) as exc:
            raise RuntimeError("eSpeak NG returned invalid audio") from exc


def _kokoro_language(language: str, fallback: str) -> str:
    return {
        "en": "a",
        "es": "e",
        "fr": "f",
        "hi": "h",
        "it": "i",
        "ja": "j",
        "pt": "p",
        "zh": "z",
    }.get(base_language(language), fallback)


def _espeak_language(language: str) -> str:
    return {"zh": "cmn"}.get(base_language(language), base_language(language))


def _whisper_language(hint: str | None, default: str) -> str:
    """Prefer an explicit language over detection.

    whisper.cpp language identification is unreliable on the short chunks the
    device records, and it confuses Bengali with neighbouring scripts. When the
    user has chosen a language, transcribe in it instead of guessing.
    """
    for candidate in (hint, default):
        if candidate and candidate.casefold() != "auto":
            return base_language(candidate)
    return "auto"
