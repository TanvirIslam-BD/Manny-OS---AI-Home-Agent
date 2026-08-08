"""Typed Manny OS configuration with YAML and environment overrides."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

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

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8765, ge=1024, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    hardware_mode: Literal["mock", "real"] = "mock"
    mcp_mode: Literal["mock", "remote_http", "local_stdio", "local_http"] = "mock"
    mcp_url: str = ""
    mcp_protocol_version: str = "2026-07-28"
    mcp_access_token: SecretStr | None = None
    mcp_connect_timeout_seconds: float = Field(default=30, gt=0, le=60)
    mcp_tool_timeout_seconds: float = Field(default=12, gt=0, le=120)
    mcp_allowed_tools: str = ""

    stt_backend: str = "mock"
    tts_backend: str = "mock"
    llm_backend: str = "mock"

    display_width: int | None = Field(default=480, ge=1)
    display_height: int | None = Field(default=480, ge=1)
    display_rotation: Literal[0, 90, 180, 270] = 0
    display_scale: float = Field(default=1.0, gt=0, le=4)

    camera_enabled: bool = True
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
        return self

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
