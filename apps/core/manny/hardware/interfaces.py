"""Protocols shielding the runtime from physical-device dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # keeps manny.hardware importable from manny.voice without a cycle
    from manny.voice.models import AudioBuffer


class LedState(StrEnum):
    BOOTING = "booting"
    READY = "ready"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    SUCCESS = "success"
    REMINDER = "reminder"
    WARNING = "warning"
    ERROR = "error"
    MUTED = "muted"
    OFFLINE = "offline"


class CameraAdapter(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def people_count(self) -> int: ...
    async def capture_frame(self) -> bytes | None: ...


class LedAdapter(Protocol):
    async def set_state(self, state: LedState) -> None: ...


class AudioInputAdapter(Protocol):
    async def set_muted(self, muted: bool) -> None: ...
    async def is_muted(self) -> bool: ...
    async def capture(self, seconds: float) -> AudioBuffer: ...


class AudioOutputAdapter(Protocol):
    async def set_volume(self, value: float) -> None: ...
    async def play(self, audio: AudioBuffer) -> None: ...


class DisplayControl(Protocol):
    async def set_brightness(self, value: float) -> None: ...


@dataclass(frozen=True, slots=True)
class HardwareBundle:
    camera: CameraAdapter
    led: LedAdapter
    audio_input: AudioInputAdapter
    audio_output: AudioOutputAdapter
    display: DisplayControl
