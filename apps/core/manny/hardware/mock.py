"""In-memory hardware adapters for simulator development and CI."""

from __future__ import annotations

from dataclasses import dataclass

from manny.hardware.interfaces import HardwareBundle, LedState


@dataclass(slots=True)
class MockCamera:
    enabled: bool = True
    running: bool = False
    simulated_people_count: int = 0

    async def start(self) -> None:
        self.running = self.enabled

    async def stop(self) -> None:
        self.running = False

    async def people_count(self) -> int:
        return self.simulated_people_count if self.running else 0


@dataclass(slots=True)
class MockLed:
    state: LedState = LedState.BOOTING

    async def set_state(self, state: LedState) -> None:
        self.state = state


@dataclass(slots=True)
class MockAudioInput:
    muted: bool = False

    async def set_muted(self, muted: bool) -> None:
        self.muted = muted

    async def is_muted(self) -> bool:
        return self.muted


@dataclass(slots=True)
class MockAudioOutput:
    volume: float = 0.7

    async def set_volume(self, value: float) -> None:
        self.volume = min(1.0, max(0.0, value))


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
