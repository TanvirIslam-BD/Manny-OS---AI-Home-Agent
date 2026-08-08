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


class SceneAnswer(BaseModel):
    """What Manny can say about the current view. The frame itself is not kept."""

    model_config = ConfigDict(frozen=True)

    answer: str = Field(min_length=1, max_length=600)
    language: str = Field(default="en", min_length=2, max_length=35)
