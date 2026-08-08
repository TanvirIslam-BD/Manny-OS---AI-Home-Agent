from datetime import UTC, datetime, time, timedelta

from manny.notifications import AlertEngine, DeliveryDecision, Notification, Severity
from manny.state import PrivacyState


def reminder(now: datetime) -> Notification:
    return Notification(
        event_id="payment-demo",
        title="Upcoming payment",
        message="A fictional payment is due tomorrow",
        severity=Severity.REMINDER,
        first_seen=now,
        expires_at=now + timedelta(days=2),
        cooldown_seconds=3600,
    )


def test_due_payment_delivers_once_then_respects_cooldown() -> None:
    now = datetime(2026, 8, 8, 12, tzinfo=UTC)
    engine = AlertEngine(time(22), time(7))
    item = reminder(now)

    first = engine.decide(item, now=now, present=True, privacy=PrivacyState.PRESENT_TRUSTED)
    repeated = engine.decide(
        item,
        now=now + timedelta(minutes=5),
        present=True,
        privacy=PrivacyState.PRESENT_TRUSTED,
    )
    assert first is DeliveryDecision.DELIVER
    assert repeated is DeliveryDecision.SUPPRESS


def test_quiet_hours_and_absence_queue_noncritical_alert() -> None:
    now = datetime(2026, 8, 8, 23, tzinfo=UTC)
    engine = AlertEngine(time(22), time(7))
    assert (
        engine.decide(reminder(now), now=now, present=True, privacy=PrivacyState.PRESENT_TRUSTED)
        is DeliveryDecision.QUEUE
    )
    assert (
        engine.decide(reminder(now), now=now, present=False, privacy=PrivacyState.PRESENT_TRUSTED)
        is DeliveryDecision.QUEUE
    )
