"""Configurable Linux/Raspberry Pi hardware adapters."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from pathlib import Path

from manny.config import Settings
from manny.hardware.interfaces import HardwareBundle, LedState
from manny.vision import Picamera2Adapter, build_person_detector
from manny.voice.models import AudioBuffer

logger = logging.getLogger(__name__)
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


def _control_device(pcm_device: str) -> str:
    """Turn a PCM device name into the control device `amixer` expects.

    Capture and playback address a PCM ("hw:Loopback,0,0"); the mixer addresses the
    card ("hw:Loopback"). Passing the PCM name to amixer is an error, so the
    subdevice components are dropped, and plughw is a PCM-only wrapper with no
    mixer of its own.
    """
    device = pcm_device.split(",", 1)[0]
    if device.startswith("plughw:"):
        return "hw:" + device.removeprefix("plughw:")
    return device


@dataclass(slots=True)
class AlsaAudioInput:
    """Microphone capture through `arecord`, emitting signed 16-bit little-endian PCM."""

    device: str
    muted: bool = False
    sample_rate: int = 16_000
    channels: int = 1

    async def set_muted(self, muted: bool) -> None:
        # The flag is what actually mutes: capture() returns empty PCM while it is
        # set, and nothing reaches the recogniser. The mixer call is an additional
        # hardware mute, and it is best-effort on purpose — control names differ per
        # card ("Capture", "Mic", none at all), so a card without the control used to
        # raise CalledProcessError out of the API and leave the microphone live. A
        # privacy control must not fail because a mixer name did not match.
        self.muted = muted
        try:
            await _run(
                "amixer", "-D", _control_device(self.device),
                "sset", "Capture", "nocap" if muted else "cap",
            )
        except Exception:
            logger.info(
                "no ALSA capture control on %s; relying on the software mute",
                self.device,
                exc_info=True,
            )

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

    async def stream(self, frame_seconds: float) -> AsyncGenerator[AudioBuffer, None]:
        """Read the microphone continuously in small frames.

        One long-lived `arecord` rather than a subprocess per chunk. The old
        fixed-length capture left an ALSA open/close and an idle gap between
        chunks, so speech that straddled a boundary was lost outright; here the
        stream is unbroken for as long as the caller keeps reading.
        """
        if self.muted:
            return
        frame_bytes = max(
            2, int(self.sample_rate * self.channels * _SAMPLE_BYTES * frame_seconds)
        )
        frame_bytes -= frame_bytes % (self.channels * _SAMPLE_BYTES)
        process = await asyncio.create_subprocess_exec(
            "arecord",
            "-D", self.device,
            "-t", "raw",
            "-f", "S16_LE",
            "-r", str(self.sample_rate),
            "-c", str(self.channels),
            "-q",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout = process.stdout
        if stdout is None:  # pragma: no cover - PIPE always provides one
            raise RuntimeError("arecord produced no output stream")
        try:
            while True:
                try:
                    pcm = await stdout.readexactly(frame_bytes)
                except asyncio.IncompleteReadError:
                    return
                yield AudioBuffer(
                    pcm=pcm, sample_rate=self.sample_rate, channels=self.channels
                )
        finally:
            # The caller stops reading as soon as the utterance ends, so the
            # recorder must be torn down here or every turn would leak one.
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2.0)
                except TimeoutError:
                    process.kill()
                    await process.wait()


@dataclass(slots=True)
class AlsaAudioOutput:
    """Speaker playback through `aplay`, consuming signed 16-bit little-endian PCM."""

    device: str

    async def set_volume(self, value: float) -> None:
        percent = round(min(1.0, max(0.0, value)) * 100)
        # Same reasoning as capture mute: "Master" does not exist on every card, and
        # a missing mixer control should not turn a volume change into a 500.
        try:
            await _run(
                "amixer", "-D", _control_device(self.device), "sset", "Master", f"{percent}%"
            )
        except Exception:
            logger.info(
                "no ALSA Master control on %s; volume unchanged", self.device, exc_info=True
            )

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
