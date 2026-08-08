"""Public MCP connection models with no credential-bearing fields."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MCPConnectionPhase(StrEnum):
    MOCK = "mock"
    DISABLED = "disabled"
    CONNECTING = "connecting"
    AUTH_REQUIRED = "auth_required"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    ERROR = "error"


class MCPStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    phase: MCPConnectionPhase
    connected: bool = False
    server_name: str = "Money Copilot MCP"
    protocol_version: str | None = None
    authorization_url: str | None = None
    discovered_tools: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    detail: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
