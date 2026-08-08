import io
import json
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from manny.agent import RuleBasedAgent, ToolBroker
from manny.mcp import MockMCPClient
from manny.policy import PolicyEngine
from manny.state import PrivacyState, RuntimeState, StateMachine
from manny.voice import (
    AudioBuffer,
    EspeakTextToSpeech,
    HalfDuplexVoiceCoordinator,
    KokoroTextToSpeech,
    MockSpeechToText,
    MockTextToSpeech,
    MockVoiceActivity,
    MockWakeWord,
    MoonshineSpeechToText,
    WhisperCppSpeechToText,
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


@pytest.mark.asyncio
async def test_whisper_cpp_returns_detected_language(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    binary = tmp_path / "whisper-cli"
    model = tmp_path / "ggml-base.bin"

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        output_base = Path(command[command.index("-of") + 1])
        output_base.with_suffix(".json").write_text(
            json.dumps(
                {
                    "result": {"language": "bn"},
                    "transcription": [{"text": " আমার বাজেট কত?"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        assert command[command.index("-l") + 1] == "auto"
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr("manny.voice.local.subprocess.run", run)
    transcript = await WhisperCppSpeechToText(binary=binary, model=model).transcribe(
        AudioBuffer(pcm=b"\x00\x00" * 40)
    )

    assert transcript.text == "আমার বাজেট কত?"
    assert transcript.language == "bn"


@pytest.mark.asyncio
async def test_espeak_uses_language_voice_and_returns_pcm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        assert command[command.index("-v") + 1] == "bn"
        assert kwargs["input"] == "স্বাগতম".encode()
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(22_050)
            target.writeframes(b"\x00\x00" * 20)
        return subprocess.CompletedProcess(command, 0, output.getvalue(), b"")

    monkeypatch.setattr("manny.voice.local.subprocess.run", run)
    audio = await EspeakTextToSpeech(tmp_path / "espeak-ng").synthesize(
        "স্বাগতম", "manny", "bn-BD"
    )

    assert audio.sample_rate == 22_050
    assert audio.language_hint == "bn-BD"
