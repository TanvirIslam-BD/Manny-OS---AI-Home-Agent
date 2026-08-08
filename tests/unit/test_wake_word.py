"""Wake-phrase gating: the device must ignore speech not addressed to it."""

from __future__ import annotations

import pytest

from manny.agent import RuleBasedAgent, ToolBroker
from manny.hardware.mock import MockAudioInput, MockAudioOutput
from manny.mcp import MockMCPClient
from manny.policy import PolicyEngine
from manny.state import StateMachine
from manny.voice import (
    HalfDuplexVoiceCoordinator,
    MockSpeechToText,
    MockTextToSpeech,
    MockVoiceActivity,
    PhraseWakeWord,
    VoiceLoop,
)


def build_loop(*, wake: bool = True, follow_up: float = 8.0) -> tuple[VoiceLoop, MockAudioInput]:
    state = StateMachine()
    agent = RuleBasedAgent(ToolBroker(MockMCPClient(), PolicyEngine()), remote=False)
    coordinator = HalfDuplexVoiceCoordinator(
        stt=MockSpeechToText(),
        tts=MockTextToSpeech(),
        vad=MockVoiceActivity(),
        agent=agent,
        state=state,
        speaker=MockAudioOutput(),
    )
    microphone = MockAudioInput()
    loop = VoiceLoop(
        microphone,
        coordinator,
        state,
        wake_word=PhraseWakeWord(MockSpeechToText()) if wake else None,
        follow_up_seconds=follow_up,
    )
    return loop, microphone


def wake_word() -> PhraseWakeWord:
    return PhraseWakeWord(MockSpeechToText())


@pytest.mark.parametrize(
    "spoken",
    ["hey manny", "Hey Manny!", "  hi manny  ", "ok manny", "hello manny", "hey manny?"],
)
def test_wake_phrases_are_recognised(spoken: str) -> None:
    assert wake_word().matches(spoken) is True


@pytest.mark.parametrize(
    "spoken",
    [
        "what time is it",
        "did you see the game last night",
        "manny is a nice name",  # the name alone must not wake it
        "",
    ],
)
def test_ordinary_conversation_does_not_wake_the_device(spoken: str) -> None:
    assert wake_word().matches(spoken) is False


def test_recognition_slips_still_wake_the_device() -> None:
    # whisper commonly returns these for "hey manny".
    assert wake_word().matches("hey many how is my budget") is True
    assert wake_word().matches("hay manny") is True


def test_the_phrase_is_stripped_so_the_command_survives() -> None:
    detector = wake_word()

    assert detector.without_phrase("Hey Manny, how is my budget?") == "how is my budget"
    assert detector.without_phrase("hi manny what is the weather") == "what is the weather"
    # Nothing after the phrase leaves the original text rather than an empty query.
    assert detector.without_phrase("hey manny") == "hey manny"


async def test_speech_without_the_wake_phrase_is_ignored() -> None:
    loop, microphone = build_loop()
    microphone.simulated_pcm = b"how is my budget"

    assert await loop.poll_once() is None


async def test_the_wake_phrase_starts_a_turn_and_carries_the_command() -> None:
    loop, microphone = build_loop()
    microphone.simulated_pcm = b"hey manny how is my budget"

    result = await loop.poll_once()

    assert result is not None
    assert result.transcript.text == "how is my budget"
    assert "spent" in result.answer.casefold()


async def test_a_follow_up_needs_no_second_wake_phrase() -> None:
    loop, microphone = build_loop()
    microphone.simulated_pcm = b"hey manny hello"
    assert await loop.poll_once() is not None

    microphone.simulated_pcm = b"how is my budget"
    follow_up = await loop.poll_once()

    assert follow_up is not None
    assert follow_up.transcript.text == "how is my budget"


async def test_the_follow_up_window_closes() -> None:
    loop, microphone = build_loop(follow_up=0)
    microphone.simulated_pcm = b"hey manny hello"
    assert await loop.poll_once() is not None

    microphone.simulated_pcm = b"how is my budget"

    # Once the window lapses the device is deaf again until addressed.
    assert await loop.poll_once() is None


async def test_disabling_the_wake_word_answers_any_speech() -> None:
    loop, microphone = build_loop(wake=False)
    microphone.simulated_pcm = b"how is my budget"

    assert await loop.poll_once() is not None
