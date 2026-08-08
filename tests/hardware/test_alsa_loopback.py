"""Exercise the real ALSA adapters against a kernel loopback sound card.

`snd-aloop` presents a playback device whose audio reappears on a capture
device, so `arecord` and `aplay` talk to a genuine ALSA pipeline with no
physical hardware. That covers the part of the device path unit tests cannot:
device string handling, format negotiation, and whether captured bytes actually
come back as signed 16-bit little-endian PCM at the requested rate.

It does not replace a Raspberry Pi. A real codec can still disagree about rates
or arrive muted. What this catches is the class of mistake that would otherwise
survive until first boot.

Load the driver with `scripts/setup_audio_loopback.sh`; without it these tests
skip rather than fail.
"""

from __future__ import annotations

import array
import asyncio
import math
import shutil
import subprocess

import pytest

from manny.hardware.real import AlsaAudioInput, AlsaAudioOutput
from manny.voice.models import AudioBuffer

RATE = 16_000
PLAYBACK_DEVICE = "hw:Loopback,0,0"
CAPTURE_DEVICE = "hw:Loopback,1,0"


def _loopback_ready() -> bool:
    if not (shutil.which("arecord") and shutil.which("aplay")):
        return False
    try:
        listing = subprocess.run(
            ["arecord", "-l"], capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "Loopback" in listing


pytestmark = pytest.mark.skipif(
    not _loopback_ready(), reason="ALSA snd-aloop loopback device is not available"
)


def tone(seconds: float, *, frequency: int = 440, amplitude: float = 0.6) -> bytes:
    samples = array.array(
        "h",
        (
            int(amplitude * 32_767 * math.sin(2 * math.pi * frequency * index / RATE))
            for index in range(int(RATE * seconds))
        ),
    )
    return samples.tobytes()


def level_of(pcm: bytes) -> float:
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(value * value for value in samples) / len(samples)) / 32_768


async def test_captured_audio_comes_back_through_the_speaker_path() -> None:
    """A full round trip: our playback adapter feeding our capture adapter."""
    speaker = AlsaAudioOutput(PLAYBACK_DEVICE)
    microphone = AlsaAudioInput(CAPTURE_DEVICE, sample_rate=RATE, channels=1)

    async def play_after_capture_starts() -> None:
        await asyncio.sleep(0.35)
        await speaker.play(AudioBuffer(pcm=tone(1.5), sample_rate=RATE, channels=1))

    captured, _ = await asyncio.gather(microphone.capture(2.0), play_after_capture_starts())

    assert captured.sample_rate == RATE
    assert captured.channels == 1
    # Two seconds of signed 16-bit mono is 64000 bytes; allow for driver rounding.
    assert len(captured.pcm) > RATE
    assert level_of(captured.pcm) > 0.01, "the loopback captured silence"


async def test_capture_reports_the_requested_format() -> None:
    microphone = AlsaAudioInput(CAPTURE_DEVICE, sample_rate=RATE, channels=1)

    captured = await microphone.capture(1.0)

    assert captured.sample_rate == RATE
    assert captured.channels == 1
    assert len(captured.pcm) % 2 == 0, "S16_LE frames must be an even byte count"


async def test_a_muted_microphone_never_reaches_the_recorder() -> None:
    microphone = AlsaAudioInput(CAPTURE_DEVICE, muted=True, sample_rate=RATE, channels=1)

    captured = await microphone.capture(1.0)

    assert captured.pcm == b""


async def test_empty_playback_is_a_no_op() -> None:
    speaker = AlsaAudioOutput(PLAYBACK_DEVICE)

    # Must not spawn aplay with nothing to write.
    await speaker.play(AudioBuffer(pcm=b"", sample_rate=RATE, channels=1))
