"""Configurable Linux/Raspberry Pi hardware adapters."""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from manny.config import Settings
from manny.hardware.interfaces import HardwareBundle, LedState
from manny.vision import Picamera2Adapter, build_person_detector
from manny.voice.models import AudioBuffer

_SAMPLE_BYTES = 2
_PROCESS_GRACE_SECONDS = 10.0


async def _run(*arguments: str) -> None:
    def execute() -> None:
        subprocess.run(arguments, check=True, capture_output=True, timeout=10)

    await asyncio.to_thread(execute)


async def _read(arguments: Sequence[str], *, timeout_seconds: float) -> bytes:
    def execute() -> bytes:
        return subprocess.run(
            arguments, check=True, capture_output=True, timeout=timeout_seconds
        ).stdout

    return await asyncio.to_thread(execute)


async def _write(
    arguments: Sequence[str], payload: bytes, *, timeout_seconds: float
) -> None:
    def execute() -> None:
        subprocess.run(
            arguments, input=payload, check=True, capture_output=True, timeout=timeout_seconds
        )

    await asyncio.to_thread(execute)


def _pcm_seconds(byte_count: int, sample_rate: int, channels: int) -> float:
    return byte_count / float(sample_rate * channels * _SAMPLE_BYTES)


@dataclass(slots=True)
class AlsaAudioInput:
    """Microphone capture through `arecord`, emitting signed 16-bit little-endian PCM."""

    device: str
    muted: bool = False
    sample_rate: int = 16_000
    channels: int = 1

    async def set_muted(self, muted: bool) -> None:
        await _run("amixer", "-D", self.device, "sset", "Capture", "nocap" if muted else "cap")
        self.muted = muted

    async def is_muted(self) -> bool:
        return self.muted

    async def capture(self, seconds: float) -> AudioBuffer:
        if self.muted:
            # A muted microphone must never reach the recorder.
            return AudioBuffer(pcm=b"", sample_rate=self.sample_rate, channels=self.channels)
        duration = max(1, round(seconds))
        pcm = await _read(
            (
                "arecord",
                "-D", self.device,
                "-t", "raw",
                "-f", "S16_LE",
                "-r", str(self.sample_rate),
                "-c", str(self.channels),
                "-d", str(duration),
                "-q",
            ),
            timeout_seconds=duration + _PROCESS_GRACE_SECONDS,
        )
        return AudioBuffer(pcm=pcm, sample_rate=self.sample_rate, channels=self.channels)


@dataclass(slots=True)
class AlsaAudioOutput:
    """Speaker playback through `aplay`, consuming signed 16-bit little-endian PCM."""

    device: str

    async def set_volume(self, value: float) -> None:
        percent = round(min(1.0, max(0.0, value)) * 100)
        await _run("amixer", "-D", self.device, "sset", "Master", f"{percent}%")

    async def play(self, audio: AudioBuffer) -> None:
        if not audio.pcm:
            return
        duration = _pcm_seconds(len(audio.pcm), audio.sample_rate, audio.channels)
        await _write(
            (
                "aplay",
                "-D", self.device,
                "-t", "raw",
                "-f", "S16_LE",
                "-r", str(audio.sample_rate),
                "-c", str(audio.channels),
                "-q",
            ),
            audio.pcm,
            timeout_seconds=duration + _PROCESS_GRACE_SECONDS,
        )


@dataclass(slots=True)
class SysfsLed:
    state_path: Path | None

    async def set_state(self, state: LedState) -> None:
        if self.state_path:
            await asyncio.to_thread(self.state_path.write_text, state.value, encoding="utf-8")


@dataclass(slots=True)
class SysfsDisplay:
    brightness_path: Path | None

    async def set_brightness(self, value: float) -> None:
        if self.brightness_path:
            scaled = round(min(1.0, max(0.0, value)) * 255)
            await asyncio.to_thread(self.brightness_path.write_text, str(scaled), encoding="utf-8")


def build_real_hardware(settings: Settings) -> HardwareBundle:
    if not settings.audio_device:
        raise RuntimeError("audio device must be configured")
    return HardwareBundle(
        camera=Picamera2Adapter(build_person_detector(settings.person_detector)),
        led=SysfsLed(settings.led_state_path),
        audio_input=AlsaAudioInput(settings.audio_device),
        audio_output=AlsaAudioOutput(settings.audio_device),
        display=SysfsDisplay(settings.display_brightness_path),
    )
