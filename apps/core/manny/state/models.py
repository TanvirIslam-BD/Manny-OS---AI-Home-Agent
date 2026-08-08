"""Runtime and privacy state models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RuntimeState(StrEnum):
    BOOTING = "BOOTING"
    PAIRING = "PAIRING"
    IDLE = "IDLE"
    PRESENT = "PRESENT"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    CONFIRMING = "CONFIRMING"
    SPEAKING = "SPEAKING"
    DASHBOARD = "DASHBOARD"
    ALERT = "ALERT"
    OFFLINE = "OFFLINE"
    CAMERA_DISABLED = "CAMERA_DISABLED"
    MIC_MUTED = "MIC_MUTED"
    ERROR = "ERROR"


class PrivacyState(StrEnum):
    PRIVATE_IDLE = "PRIVATE_IDLE"
    PRESENT_UNKNOWN = "PRESENT_UNKNOWN"
    PRESENT_TRUSTED = "PRESENT_TRUSTED"
    MULTIPLE_PEOPLE = "MULTIPLE_PEOPLE"
    PRIVACY_LOCKED = "PRIVACY_LOCKED"


class RuntimeSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: RuntimeState = RuntimeState.BOOTING
    privacy: PrivacyState = PrivacyState.PRIVATE_IDLE
    connected: bool = True
    presence: bool = False
    people_count: int = Field(default=0, ge=0)
    microphone_muted: bool = False
    camera_enabled: bool = True
    listening_enabled: bool = False
    listening_available: bool = False
    language: str = Field(default="auto", min_length=2, max_length=35)
    status_message: str = "Starting Manny"
    sequence: int = Field(default=0, ge=0)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
