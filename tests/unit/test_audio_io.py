"""Microphone capture, speaker playback, and the device listen loop."""

from __future__ import annotations

import asyncio
import struct
from math import pi, sin

import pytest

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
    Transcript,
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


class CountingWakeWord:
    """Records how often recognition was asked to run."""

    def __init__(self) -> None:
        self.transcriptions = 0

    async def transcribe(self, audio: AudioBuffer) -> Transcript:
        self.transcriptions += 1
        return await MockSpeechToText().transcribe(audio)

    def matches(self, text: str) -> bool:
        del text
        return True

    def without_phrase(self, text: str) -> str:
        return text


async def test_a_silent_chunk_never_reaches_recognition() -> None:
    # Recognition is a subprocess that wants all four Pi cores. Spending it on an
    # empty room is most of what an idle device would otherwise do.
    coordinator, state = build_coordinator(MockAudioOutput())
    wake_word = CountingWakeWord()
    microphone = MockAudioInput(simulated_pcm=silence(1.0))
    loop = VoiceLoop(
        microphone,
        coordinator,
        state,
        wake_word=wake_word,  # type: ignore[arg-type]
        # minimum_seconds=0 isolates the energy threshold: the mock recogniser reads
        # text straight out of the PCM field, so its payloads are microseconds long
        # and the duration floor alone would reject them.
        vad=EnergyVoiceActivity(threshold=0.02, minimum_seconds=0.0),
    )

    assert await loop.poll_once() is None
    assert wake_word.transcriptions == 0

    microphone.simulated_pcm = b"how is my budget"

    result = await loop.poll_once()

    assert result is not None
    assert result.transcript.text == "how is my budget"
    assert wake_word.transcriptions == 1


async def test_a_typed_question_is_answered_on_real_voice_backends() -> None:
    # The device uses energy voice activity, which measures the PCM's duration. A
    # typed question carried in the PCM field is microseconds long, so routing text
    # through the audio stages failed as "No speech detected" on hardware while
    # passing against the mocks.
    state = StateMachine()
    agent = RuleBasedAgent(ToolBroker(MockMCPClient(), PolicyEngine()), remote=False)
    coordinator = HalfDuplexVoiceCoordinator(
        stt=MockSpeechToText(),
        tts=MockTextToSpeech(),
        vad=EnergyVoiceActivity(threshold=0.02),
        agent=agent,
        state=state,
        speaker=MockAudioOutput(),
    )

    with pytest.raises(ValueError):
        await coordinator.run_turn(
            AudioBuffer(pcm=b"how is my budget"), privacy=PrivacyState.PRIVATE_IDLE
        )

    result = await coordinator.run_text_turn(
        "how is my budget", privacy=PrivacyState.PRIVATE_IDLE
    )

    assert result.transcript.text == "how is my budget"
    assert result.answer


async def test_an_empty_typed_question_is_rejected() -> None:
    coordinator, _ = build_coordinator(MockAudioOutput())

    with pytest.raises(ValueError):
        await coordinator.run_text_turn("   ", privacy=PrivacyState.PRIVATE_IDLE)


class CountingMicrophone:
    """Records how often the recorder was actually started."""

    def __init__(self, pcm: bytes) -> None:
        self.pcm = pcm
        self.captures = 0

    async def is_muted(self) -> bool:
        return False

    async def capture(self, seconds: float) -> AudioBuffer:
        del seconds
        self.captures += 1
        return AudioBuffer(pcm=self.pcm)


async def test_the_loop_does_not_record_over_a_running_turn() -> None:
    # It used to capture and transcribe straight through the reply, competing with
    # the model generating it, then discard the transcript on VoiceBusyError.
    coordinator, state = build_coordinator(MockAudioOutput())
    microphone = CountingMicrophone(b"how is my budget")
    loop = VoiceLoop(microphone, coordinator, state)  # type: ignore[arg-type]

    async def occupy() -> None:
        async with coordinator._turn_lock:
            await asyncio.sleep(0.05)

    holder = asyncio.create_task(occupy())
    await asyncio.sleep(0)
    try:
        assert coordinator.busy is True
        assert await loop.poll_once() is None
        assert microphone.captures == 0
    finally:
        await holder

    assert coordinator.busy is False
    assert await loop.poll_once() is not None
    assert microphone.captures == 1
