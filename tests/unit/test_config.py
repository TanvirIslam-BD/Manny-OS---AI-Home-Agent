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


def test_voice_loop_is_on_by_default_but_only_runs_on_real_hardware() -> None:
    desktop = Settings(hardware_mode="mock", _env_file=None)
    device = Settings(hardware_mode="real", audio_device="default", _env_file=None)

    assert desktop.voice_loop_enabled is True
    assert desktop.voice_loop_active is False
    assert device.voice_loop_active is True

    disabled = Settings(
        hardware_mode="real",
        audio_device="default",
        voice_loop_enabled=False,
        _env_file=None,
    )
    assert disabled.voice_loop_active is False


def test_vision_and_conversation_share_one_local_runtime() -> None:
    settings = Settings(_env_file=None)

    # Under llama.cpp these had to differ: one server served one model, so vision
    # needed its own port and its own weights. One Ollama daemon serves many models,
    # and the chosen model is multimodal, so both now point at the same place —
    # a simplification ADR-020 exists to record.
    assert settings.vision_language_base_url == settings.llm_base_url
    assert settings.vision_language_model == settings.llm_model

    # Sharing the endpoint must not weaken the loopback rule for either of them.
    with pytest.raises(ValidationError):
        Settings(vision_language_base_url="https://vision.example.com", _env_file=None)
    with pytest.raises(ValidationError):
        Settings(llm_base_url="http://10.0.0.5:11434", _env_file=None)


def test_production_refuses_to_start_without_a_credential_vault() -> None:
    with pytest.raises(ValidationError, match="keyring"):
        Settings(environment="production", mcp_token_storage="json", _env_file=None)

    assert (
        Settings(
            environment="production", mcp_token_storage="keyring", _env_file=None
        ).mcp_token_storage
        == "keyring"
    )


def test_raspberry_pi_is_deliberately_exempt_from_the_vault_requirement() -> None:
    # Not an oversight, and not to be "fixed" by extending the rule above: a headless
    # appliance has to reconnect after a power cut with nobody present, so a vault
    # would have to unlock itself from the same SD card that holds the tokens, and
    # Pi 5 has no TPM to bind the key to instead. See ADR-013 and docs/security.md,
    # which state the resulting exposure rather than implying protection.
    settings = Settings(environment="raspberrypi", mcp_token_storage="json", _env_file=None)

    assert settings.mcp_token_storage == "json"


def test_only_implemented_mcp_transports_are_accepted() -> None:
    # local_stdio and local_http used to be accepted and unimplemented: anything but
    # remote_http falls through to the mock client, so selecting them served demo data
    # that looked live, which the honest-degradation invariant forbids. Rejecting them by
    # name is the difference between a startup error and silently fabricated finance data.
    for mode in ("local_stdio", "local_http"):
        with pytest.raises(ValidationError, match="mcp_mode"):
            Settings(mcp_mode=mode, _env_file=None)

    assert Settings(mcp_mode="mock", _env_file=None).mcp_mode == "mock"
