"""In-memory hardware adapters for simulator development and CI."""

from __future__ import annotations

from dataclasses import dataclass, field

from manny.hardware.interfaces import HardwareBundle, LedState
from manny.voice.models import AudioBuffer


@dataclass(slots=True)
class MockCamera:
    enabled: bool = True
    running: bool = False
    simulated_people_count: int = 0
    # A JPEG magic number so backends see plausible bytes without a real camera.
    simulated_frame: bytes = b"\xff\xd8\xff\xdb simulated frame"

    async def start(self) -> None:
        self.running = self.enabled

    async def stop(self) -> None:
        self.running = False

    async def people_count(self) -> int:
        return self.simulated_people_count if self.running else 0

    async def capture_frame(self) -> bytes | None:
        return self.simulated_frame if self.running else None


@dataclass(slots=True)
class MockLed:
    state: LedState = LedState.BOOTING

    async def set_state(self, state: LedState) -> None:
        self.state = state


@dataclass(slots=True)
class MockAudioInput:
    muted: bool = False
    simulated_pcm: bytes = b""

    async def set_muted(self, muted: bool) -> None:
        self.muted = muted

    async def is_muted(self) -> bool:
        return self.muted

    async def capture(self, seconds: float) -> AudioBuffer:
        del seconds
        return AudioBuffer(pcm=b"" if self.muted else self.simulated_pcm)


@dataclass(slots=True)
class MockAudioOutput:
    volume: float = 0.7
    played: list[AudioBuffer] = field(default_factory=list)

    async def set_volume(self, value: float) -> None:
        self.volume = min(1.0, max(0.0, value))

    async def play(self, audio: AudioBuffer) -> None:
        self.played.append(audio)


@dataclass(slots=True)
class MockDisplay:
    brightness: float = 0.8

    async def set_brightness(self, value: float) -> None:
        self.brightness = min(1.0, max(0.0, value))


def build_mock_hardware(*, camera_enabled: bool = True) -> HardwareBundle:
    return HardwareBundle(
        camera=MockCamera(enabled=camera_enabled),
        led=MockLed(),
        audio_input=MockAudioInput(),
        audio_output=MockAudioOutput(),
        display=MockDisplay(),
    )
