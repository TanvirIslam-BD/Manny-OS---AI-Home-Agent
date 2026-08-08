from pathlib import Path
from types import SimpleNamespace

import pytest

from manny.agent import RuleBasedAgent, ToolBroker
from manny.mcp import MockMCPClient
from manny.policy import PolicyEngine
from manny.state import PrivacyState, RuntimeState, StateMachine
from manny.voice import (
    AudioBuffer,
    HalfDuplexVoiceCoordinator,
    KokoroTextToSpeech,
    MockSpeechToText,
    MockTextToSpeech,
    MockVoiceActivity,
    MockWakeWord,
    MoonshineSpeechToText,
)


@pytest.mark.asyncio
async def test_wake_word_is_detected_locally() -> None:
    assert await MockWakeWord().detected(AudioBuffer(pcm=b"Hey Manny")) is True


@pytest.mark.asyncio
async def test_half_duplex_voice_turn_calls_agent_and_synthesizes_answer() -> None:
    state = StateMachine()
    agent = RuleBasedAgent(ToolBroker(MockMCPClient(), PolicyEngine()), remote=False)
    voice = HalfDuplexVoiceCoordinator(
        stt=MockSpeechToText(),
        tts=MockTextToSpeech(),
        vad=MockVoiceActivity(),
        agent=agent,
        state=state,
    )

    result = await voice.run_turn(
        AudioBuffer(pcm=b"How's my budget?"), privacy=PrivacyState.PRIVATE_IDLE
    )

    assert result.tool_name == "money.get_budget_summary"
    assert b"$560.00 remaining" in result.audio.pcm
    assert state.snapshot.state is RuntimeState.SPEAKING


@pytest.mark.asyncio
async def test_moonshine_adapter_removes_temporary_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Path] = []

    def transcribe(path: Path, model: str) -> list[str]:
        assert model == "moonshine/tiny"
        assert path.exists()
        captured.append(path)
        return ["hello manny"]

    monkeypatch.setitem(
        __import__("sys").modules, "moonshine_onnx", SimpleNamespace(transcribe=transcribe)
    )
    result = await MoonshineSpeechToText().transcribe(AudioBuffer(pcm=b"\x00\x00" * 20))
    assert result.text == "hello manny"
    assert captured and not captured[0].exists()


@pytest.mark.asyncio
async def test_kokoro_adapter_returns_pcm(monkeypatch: pytest.MonkeyPatch) -> None:
    class Pipeline:
        def __init__(self, lang_code: str) -> None:
            assert lang_code == "a"

        def __call__(self, text: str, voice: str):  # type: ignore[no-untyped-def]
            assert text == "hello"
            assert voice == "manny"
            return [("hello", "hello", [0.0, 0.5, -0.5])]

    monkeypatch.setitem(__import__("sys").modules, "kokoro", SimpleNamespace(KPipeline=Pipeline))
    result = await KokoroTextToSpeech().synthesize("hello", "manny")
    assert result.sample_rate == 24_000
    assert len(result.pcm) == 6
