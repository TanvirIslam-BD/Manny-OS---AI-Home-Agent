"""Microphone capture, speaker playback, and the device listen loop."""

from __future__ import annotations

import asyncio
import struct
from math import pi, sin

from manny.agent import RuleBasedAgent, ToolBroker
from manny.hardware.mock import MockAudioInput, MockAudioOutput
from manny.mcp import MockMCPClient
from manny.policy import PolicyEngine
from manny.state import PrivacyState, RuntimeState, StateMachine
from manny.voice import (
    AudioBuffer,
    EnergyVoiceActivity,
    HalfDuplexVoiceCoordinator,
    MockSpeechToText,
    MockTextToSpeech,
    MockVoiceActivity,
    VoiceLoop,
)

RATE = 16_000


def tone(seconds: float = 1.0, amplitude: float = 0.5) -> bytes:
    count = int(RATE * seconds)
    return b"".join(
        struct.pack("<h", int(amplitude * 32_767 * sin(2 * pi * 440 * index / RATE)))
        for index in range(count)
    )


def silence(seconds: float = 1.0) -> bytes:
    return b"\x00\x00" * int(RATE * seconds)


def build_coordinator(
    speaker: MockAudioOutput,
) -> tuple[HalfDuplexVoiceCoordinator, StateMachine]:
    state = StateMachine()
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()), remote=False
    )
    coordinator = HalfDuplexVoiceCoordinator(
        stt=MockSpeechToText(),
        tts=MockTextToSpeech(),
        vad=MockVoiceActivity(),
        agent=agent,
        state=state,
        speaker=speaker,
    )
    return coordinator, state


async def test_energy_vad_separates_speech_from_silence() -> None:
    vad = EnergyVoiceActivity(threshold=0.02)

    assert await vad.contains_speech(AudioBuffer(pcm=tone())) is True
    assert await vad.contains_speech(AudioBuffer(pcm=silence())) is False
    assert await vad.contains_speech(AudioBuffer(pcm=b"")) is False


async def test_energy_vad_ignores_chunks_below_the_minimum_duration() -> None:
    vad = EnergyVoiceActivity(threshold=0.02, minimum_seconds=0.5)

    assert await vad.contains_speech(AudioBuffer(pcm=tone(seconds=0.1))) is False
    assert await vad.contains_speech(AudioBuffer(pcm=tone(seconds=0.6))) is True


async def test_muted_microphone_captures_nothing() -> None:
    microphone = MockAudioInput(simulated_pcm=b"hello manny")

    unmuted = await microphone.capture(3.0)
    await microphone.set_muted(True)
    muted = await microphone.capture(3.0)

    assert unmuted.pcm == b"hello manny"
    assert muted.pcm == b""


async def test_spoken_answer_reaches_the_speaker() -> None:
    speaker = MockAudioOutput()
    coordinator, state = build_coordinator(speaker)

    result = await coordinator.run_turn(
        AudioBuffer(pcm=b"hello"), privacy=PrivacyState.PRIVATE_IDLE
    )

    assert speaker.played, "synthesized audio must be handed to the speaker"
    assert speaker.played[-1].pcm == result.audio.pcm
    assert state.snapshot.state is RuntimeState.SPEAKING


async def test_voice_loop_skips_silence_and_runs_a_turn_on_speech() -> None:
    coordinator, state = build_coordinator(MockAudioOutput())
    microphone = MockAudioInput(simulated_pcm=b"")
    loop = VoiceLoop(microphone, coordinator, state)

    assert await loop.poll_once() is None

    microphone.simulated_pcm = b"how is my budget"
    result = await loop.poll_once()

    assert result is not None
    assert result.transcript.text == "how is my budget"


async def test_voice_loop_does_not_listen_while_muted() -> None:
    coordinator, state = build_coordinator(MockAudioOutput())
    microphone = MockAudioInput(simulated_pcm=b"how is my budget")
    await state.transition(RuntimeState.MIC_MUTED, force=True, microphone_muted=True)
    loop = VoiceLoop(microphone, coordinator, state)

    assert await loop.poll_once() is None


async def test_voice_loop_survives_a_failing_microphone() -> None:
    class BrokenMicrophone:
        async def is_muted(self) -> bool:
            return False

        async def capture(self, seconds: float) -> AudioBuffer:
            del seconds
            raise OSError("arecord is unavailable")

    coordinator, state = build_coordinator(MockAudioOutput())
    loop = VoiceLoop(BrokenMicrophone(), coordinator, state, idle_seconds=0.01)
    await loop.start()
    try:
        await asyncio.sleep(0.05)
        assert loop._task is not None and not loop._task.done()
    finally:
        await loop.stop()


async def test_capture_carries_the_configured_language_to_recognition() -> None:
    coordinator, state = build_coordinator(MockAudioOutput())
    microphone = MockAudioInput(simulated_pcm=b"kemon acho")
    loop = VoiceLoop(microphone, coordinator, state, language="bn-BD")

    result = await loop.poll_once()

    assert result is not None
    assert result.transcript.language == "bn-BD"
