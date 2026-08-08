"""Deterministic alert delivery policy with no LLM involvement."""

from datetime import datetime, time, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from manny.state import PrivacyState


class Severity(StrEnum):
    INFO = "info"
    REMINDER = "reminder"
    WARNING = "warning"
    CRITICAL = "critical"


class DeliveryDecision(StrEnum):
    DELIVER = "deliver"
    QUEUE = "queue"
    SUPPRESS = "suppress"


class Notification(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    title: str
    message: str
    severity: Severity
    first_seen: datetime
    expires_at: datetime
    cooldown_seconds: int = Field(default=3600, ge=0)
    private: bool = True


class AlertEngine:
    def __init__(self, quiet_start: time, quiet_end: time) -> None:
        self._quiet_start = quiet_start
        self._quiet_end = quiet_end
        self._last_presented: dict[str, datetime] = {}

    def decide(
        self,
        notification: Notification,
        *,
        now: datetime,
        present: bool,
        privacy: PrivacyState,
    ) -> DeliveryDecision:
        if now >= notification.expires_at:
            return DeliveryDecision.SUPPRESS
        last = self._last_presented.get(notification.event_id)
        if last and now - last < timedelta(seconds=notification.cooldown_seconds):
            return DeliveryDecision.SUPPRESS
        if not present:
            return DeliveryDecision.QUEUE
        if notification.private and privacy is not PrivacyState.PRESENT_TRUSTED:
            return DeliveryDecision.QUEUE
        if notification.severity is not Severity.CRITICAL and self._in_quiet_hours(now.time()):
            return DeliveryDecision.QUEUE
        self._last_presented[notification.event_id] = now
        return DeliveryDecision.DELIVER

    def _in_quiet_hours(self, value: time) -> bool:
        if self._quiet_start <= self._quiet_end:
            return self._quiet_start <= value < self._quiet_end
        return value >= self._quiet_start or value < self._quiet_end
