"""Typed Manny OS configuration with YAML and environment overrides."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from manny.i18n import MAJOR_LANGUAGES

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONFIG_ROOT = REPOSITORY_ROOT / "configs"


class Settings(BaseSettings):
    """Public and private runtime settings.

    Pydantic's source order is customized so environment variables override values passed
    from the selected YAML profile.
    """

    model_config = SettingsConfigDict(
        env_prefix="MANNY_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    environment: Literal["development", "raspberrypi", "production", "test"] = Field(
        default="development",
        validation_alias=AliasChoices("MANNY_ENV", "MANNY_ENVIRONMENT"),
    )
    config_profile: str = "development"
    device_id: str = "dev-manny"
    user_timezone: str = "UTC"
    data_directory: Path = REPOSITORY_ROOT / "data"

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8765, ge=1024, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    hardware_mode: Literal["mock", "real"] = "mock"
    audio_device: str | None = None
    led_state_path: Path | None = None
    display_brightness_path: Path | None = None
    mcp_mode: Literal["mock", "remote_http", "local_stdio", "local_http"] = "mock"
    mcp_url: str = ""
    mcp_protocol_version: str = "2026-07-28"
    mcp_access_token: SecretStr | None = None
    mcp_token_storage: Literal["json", "keyring"] = "json"
    mcp_connect_timeout_seconds: float = Field(default=45, gt=0, le=60)
    mcp_tool_timeout_seconds: float = Field(default=30, gt=0, le=120)
    mcp_allowed_tools: str = ""

    stt_backend: Literal["mock", "moonshine", "whisper_cpp"] = "mock"
    tts_backend: Literal["mock", "kokoro", "espeak_ng"] = "mock"
    voice_default_language: str = "auto"
    whisper_cpp_binary: Path = Path("/opt/manny/whisper.cpp/build/bin/whisper-cli")
    whisper_cpp_model: Path = Path("/opt/manny/models/ggml-base.bin")
    whisper_cpp_threads: int = Field(default=4, ge=1, le=16)
    whisper_cpp_timeout_seconds: float = Field(default=90, gt=0, le=300)
    espeak_ng_binary: Path = Path("/usr/bin/espeak-ng")
    # Speaker identifier for backends that select one. eSpeak NG picks its voice from
    # the language tag and ignores this; Kokoro requires an identifier from its own
    # catalogue and cannot invent one, so it is left empty rather than guessed.
    tts_voice: str = Field(default="", max_length=64)
    llm_backend: Literal["mock", "llama_cpp"] = "mock"
    llm_base_url: str = "http://127.0.0.1:8080"
    llm_model: str = "gemma-3-1b-it"
    llm_timeout_seconds: float = Field(default=60, gt=0, le=180)
    llm_max_tokens: int = Field(default=320, ge=32, le=512)
    llm_context_turns: int = Field(default=6, ge=1, le=12)

    display_width: int | None = Field(default=480, ge=1)
    display_height: int | None = Field(default=480, ge=1)
    display_rotation: Literal[0, 90, 180, 270] = 0
    display_scale: float = Field(default=1.0, gt=0, le=4)

    voice_loop_enabled: bool = True
    wake_word_enabled: bool = True
    wake_word_phrases: str = "hey manny,hi manny,ok manny,hello manny"
    wake_follow_up_seconds: float = Field(default=8.0, ge=0, le=60)
    voice_capture_seconds: float = Field(default=3.0, ge=1, le=15)
    voice_vad_threshold: float = Field(default=0.02, gt=0, le=1)

    # End the utterance on the speaker rather than on a clock. Without this the
    # recorder stops after voice_capture_seconds, which truncates any question
    # longer than the window and makes every short one wait out the remainder.
    # Recorders that cannot stream frames keep using the fixed window.
    voice_endpointing_enabled: bool = True
    voice_frame_seconds: float = Field(default=0.1, ge=0.02, le=0.5)
    # How much trailing silence ends a turn. Too short and Manny interrupts a pause
    # for thought; too long and every answer feels late.
    voice_silence_hold_seconds: float = Field(default=0.8, ge=0.2, le=3)
    voice_max_utterance_seconds: float = Field(default=12.0, ge=2, le=30)

    camera_enabled: bool = True
    vision_language_backend: Literal["none", "llama_cpp"] = "none"
    # A second llama-server: one instance serves one model, and a vision-capable
    # model is not the same file as the 1B text model. Point this at the text
    # server only if a single multimodal model is serving both.
    vision_language_base_url: str = "http://127.0.0.1:8081"
    vision_language_model: str = "gemma-3-4b-it"
    vision_language_timeout_seconds: float = Field(default=120, gt=0, le=300)
    person_detector: Literal["none", "opencv_hog"] = "none"
    face_recognition_enabled: bool = False
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        del settings_cls
        return env_settings, dotenv_settings, init_settings, file_secret_settings

    @field_validator("api_host")
    @classmethod
    def production_api_must_be_loopback(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Manny's local API must bind to loopback")
        return value

    @field_validator("llm_base_url", "vision_language_base_url")
    @classmethod
    def local_llm_must_be_loopback(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("local LLM URL must use HTTP on a loopback host")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("local LLM URL must not contain credentials, query, or fragment")
        return value.rstrip("/")

    @field_validator("user_timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        if value == "UTC":
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {value}") from exc
        return value

    @field_validator("face_recognition_enabled")
    @classmethod
    def face_recognition_disabled_for_v1(cls, value: bool) -> bool:
        if value:
            raise ValueError("face recognition is not enabled for the Manny V1 scaffold")
        return value

    @model_validator(mode="after")
    def validate_remote_mcp(self) -> Settings:
        if self.mcp_mode == "remote_http":
            if not self.mcp_url:
                raise ValueError("MANNY_MCP_URL is required for remote_http mode")
            if not self.mcp_url.startswith("https://"):
                raise ValueError("remote MCP connections require HTTPS")
        # Deliberately not extended to raspberrypi. The Pi is a headless appliance
        # that must restore its connection after a power cut with nobody present, so
        # any vault it uses has to unlock itself, which puts the unlocking secret on
        # the same SD card as the tokens. Pi 5 has no TPM to bind it to, so an
        # auto-unlocked vault is a mode-0600 file plus a daemon that can strand the
        # device — more failure surface for no gain against the threat that matters,
        # someone taking the card. The Pi profile therefore uses json storage and
        # docs/security.md states that exposure instead of implying otherwise.
        if self.environment == "production" and self.mcp_token_storage != "keyring":
            raise ValueError("production requires OS keyring token storage")
        if self.hardware_mode == "real" and not self.audio_device:
            raise ValueError("real hardware mode requires MANNY_AUDIO_DEVICE")
        if not self.data_directory.is_absolute():
            raise ValueError("MANNY_DATA_DIRECTORY must be an absolute path")
        return self

    @property
    def wake_phrases(self) -> tuple[str, ...]:
        return tuple(
            phrase.strip() for phrase in self.wake_word_phrases.split(",") if phrase.strip()
        )

    @property
    def voice_loop_active(self) -> bool:
        """The listen loop is on by default but only runs against a real microphone."""

        return self.voice_loop_enabled and self.hardware_mode == "real"

    @property
    def allowed_mcp_tools(self) -> frozenset[str]:
        return frozenset(name.strip() for name in self.mcp_allowed_tools.split(",") if name.strip())

    def public_dict(self) -> dict[str, Any]:
        """Return browser-safe configuration only."""

        return {
            "environment": self.environment,
            "deviceId": self.device_id,
            "timezone": self.user_timezone,
            "hardwareMode": self.hardware_mode,
            "mcpMode": self.mcp_mode,
            "display": {
                "width": self.display_width,
                "height": self.display_height,
                "rotation": self.display_rotation,
                "scale": self.display_scale,
            },
            "cameraEnabled": self.camera_enabled,
            "faceRecognitionEnabled": self.face_recognition_enabled,
            "voice": {
                "defaultLanguage": self.voice_default_language,
                "majorLanguages": MAJOR_LANGUAGES,
                "automaticDetection": self.stt_backend == "whisper_cpp",
                "loopEnabled": self.voice_loop_enabled,
                "wakeWordEnabled": self.wake_word_enabled,
                "wakePhrases": list(self.wake_phrases),
                "loopAvailable": self.voice_loop_active,
                "captureSeconds": self.voice_capture_seconds,
                "vadThreshold": self.voice_vad_threshold,
            },
            "presence": {
                "detector": self.person_detector,
                "sceneDescription": self.vision_language_backend != "none",
                "available": self.person_detector != "none",
            },
        }


def _read_profile(profile: str) -> dict[str, Any]:
    if not profile.replace("-", "").replace("_", "").isalnum():
        raise ValueError("invalid configuration profile name")
    profile_path = CONFIG_ROOT / f"{profile}.yaml"
    if not profile_path.exists():
        return {}
    data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"configuration profile must contain a mapping: {profile_path}")
    return data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    profile = os.getenv("MANNY_CONFIG_PROFILE", "development")
    return Settings(config_profile=profile, **_read_profile(profile))
