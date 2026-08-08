"""Configurable Linux/Raspberry Pi hardware adapters."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path

from manny.config import Settings
from manny.hardware.interfaces import HardwareBundle, LedState
from manny.vision import Picamera2Adapter


async def _run(*arguments: str) -> None:
    def execute() -> None:
        subprocess.run(arguments, check=True, capture_output=True, timeout=10)

    await asyncio.to_thread(execute)


@dataclass(slots=True)
class AlsaAudioInput:
    device: str
    muted: bool = False

    async def set_muted(self, muted: bool) -> None:
        await _run("amixer", "-D", self.device, "sset", "Capture", "nocap" if muted else "cap")
        self.muted = muted

    async def is_muted(self) -> bool:
        return self.muted


@dataclass(slots=True)
class AlsaAudioOutput:
    device: str

    async def set_volume(self, value: float) -> None:
        percent = round(min(1.0, max(0.0, value)) * 100)
        await _run("amixer", "-D", self.device, "sset", "Master", f"{percent}%")


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
        camera=Picamera2Adapter(),
        led=SysfsLed(settings.led_state_path),
        audio_input=AlsaAudioInput(settings.audio_device),
        audio_output=AlsaAudioOutput(settings.audio_device),
        display=SysfsDisplay(settings.display_brightness_path),
    )
