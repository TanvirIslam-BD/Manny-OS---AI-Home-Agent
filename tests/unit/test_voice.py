import io
import json
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from manny.agent import RuleBasedAgent, ToolBroker
from manny.lifecycle import _espeak_binary
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


def test_whisper_language_prefers_an_explicit_choice_over_detection() -> None:
    from manny.voice.local import _whisper_language

    # A configured language must win, so Bangla is not left to chunk detection.
    assert _whisper_language("bn-BD", "auto") == "bn"
    assert _whisper_language(None, "bn-BD") == "bn"
    assert _whisper_language("auto", "bn-BD") == "bn"
    # Detection stays available when nothing is configured.
    assert _whisper_language(None, "auto") == "auto"
    assert _whisper_language(None, "") == "auto"
    assert _whisper_language("zh-CN", "auto") == "zh"


def test_reply_language_follows_the_answer_not_a_romanized_question() -> None:
    from manny.agent.runtime import _spoken_language

    # "Amar sathe Bangla kotha bolo" is Latin script and detects as English, but
    # the reply is Bangla and drives the text-to-speech voice.
    assert _spoken_language("আমি ভালো আছি", "en") == "bn"
    # A Latin reply keeps whatever the request resolved to.
    assert _spoken_language("I'm doing well", "bn-BD") == "bn-BD"
    assert _spoken_language("I'm doing well", "en") == "en"


def test_audio_is_packaged_as_a_wav_a_browser_can_decode() -> None:
    # Adapters return bare PCM because the speaker adapters take it directly. A
    # browser needs the container, and getting the header wrong is silent: the
    # element simply refuses to play.
    buffer = AudioBuffer(pcm=b"\x00\x01" * 300, sample_rate=22_050, channels=1)

    with wave.open(io.BytesIO(buffer.to_wav()), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 22_050
        assert audio.readframes(audio.getnframes()) == buffer.pcm


@pytest.mark.asyncio
async def test_a_shown_reply_can_be_spoken_without_running_a_turn() -> None:
    # The simulator answers over /api/agent/query and never touches the coordinator,
    # so speaking that reply has to work outside a voice turn.
    state = StateMachine()
    agent = RuleBasedAgent(ToolBroker(MockMCPClient(), PolicyEngine()), remote=False)
    voice = HalfDuplexVoiceCoordinator(
        stt=MockSpeechToText(),
        tts=MockTextToSpeech(),
        vad=MockVoiceActivity(),
        agent=agent,
        state=state,
    )

    audio = await voice.synthesize("আপনার বাজেট ভালো আছে।", language="bn")

    assert audio.pcm == "আপনার বাজেট ভালো আছে।".encode()
    with pytest.raises(ValueError):
        await voice.synthesize("   ", language="bn")


def test_espeak_is_found_on_path_when_it_is_not_where_linux_puts_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The default points at the Pi installer's location. A desktop developer on
    # Windows or macOS has it elsewhere, and requiring a per-platform path in every
    # profile is what keeps people on browser voices that cannot speak Bengali.
    installed = tmp_path / "espeak-ng.exe"
    installed.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "manny.lifecycle.shutil.which",
        lambda name: str(installed) if name == "espeak-ng" else None,
    )

    assert _espeak_binary(Path("/usr/bin/espeak-ng")) == installed


def test_an_unresolvable_espeak_is_returned_unchanged_rather_than_substituted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Returning some other program would be worse than failing: synthesis must fail
    # loudly rather than speak with whatever happened to be on PATH.
    monkeypatch.setattr("manny.lifecycle.shutil.which", lambda _name: None)

    assert _espeak_binary(Path("/usr/bin/espeak-ng")) == Path("/usr/bin/espeak-ng")
