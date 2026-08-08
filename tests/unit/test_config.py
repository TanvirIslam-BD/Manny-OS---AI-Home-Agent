import pytest
from pydantic import ValidationError

from manny.config import Settings


def test_public_settings_do_not_include_mcp_url() -> None:
    settings = Settings(mcp_url="https://private.example/mcp")

    public = settings.public_dict()

    assert "mcp_url" not in public
    assert "mcpUrl" not in public


def test_non_loopback_api_binding_is_rejected() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(api_host="0.0.0.0")


def test_local_llm_cannot_send_conversation_to_remote_host() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(llm_base_url="https://models.example.test")


def test_face_recognition_cannot_be_silently_enabled() -> None:
    with pytest.raises(ValidationError, match="face recognition"):
        Settings(face_recognition_enabled=True)


def test_documented_environment_variable_name_is_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANNY_ENV", "test")

    assert Settings().environment == "test"


def test_iana_timezone_is_portable() -> None:
    assert Settings(user_timezone="America/New_York").user_timezone == "America/New_York"


def test_remote_mcp_requires_https() -> None:
    with pytest.raises(ValidationError, match="require HTTPS"):
        Settings(mcp_mode="remote_http", mcp_url="http://example.test/mcp", _env_file=None)


def test_mcp_tool_allowlist_is_parsed() -> None:
    settings = Settings(
        mcp_allowed_tools="money.get_budget_summary, money.get_transactions",
        _env_file=None,
    )

    assert settings.allowed_mcp_tools == {
        "money.get_budget_summary",
        "money.get_transactions",
    }


def test_public_settings_advertise_multilingual_voice() -> None:
    settings = Settings(
        stt_backend="whisper_cpp",
        tts_backend="espeak_ng",
        _env_file=None,
    )

    voice = settings.public_dict()["voice"]

    assert isinstance(voice, dict)
    assert voice["automaticDetection"] is True
    assert voice["majorLanguages"]["bn"] == "বাংলা"
