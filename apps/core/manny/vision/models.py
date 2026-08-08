"""Privacy-preserving vision events contain metadata, never frames."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class PresenceEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str = "presence.changed"
    present: bool
    people_count: int = Field(ge=0)
    confidence: float = Field(default=1.0, ge=0, le=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
