from pathlib import Path

from manny.config import Settings
from manny.hardware import build_real_hardware
from manny.hardware.interfaces import LedState
from manny.hardware.real import SysfsDisplay, SysfsLed


async def test_sysfs_led_and_display_use_configured_paths(tmp_path: Path) -> None:
    led_path = tmp_path / "led"
    brightness_path = tmp_path / "brightness"
    led_path.touch()
    brightness_path.touch()

    await SysfsLed(led_path).set_state(LedState.LISTENING)
    await SysfsDisplay(brightness_path).set_brightness(0.5)

    assert led_path.read_text() == "listening"
    assert brightness_path.read_text() == "128"


def test_real_bundle_does_not_hard_code_audio_device() -> None:
    settings = Settings(hardware_mode="real", audio_device="hw:CARD=Test", _env_file=None)
    bundle = build_real_hardware(settings)
    assert bundle.audio_input.device == "hw:CARD=Test"  # type: ignore[attr-defined]
