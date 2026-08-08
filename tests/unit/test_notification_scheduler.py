from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from manny.notifications import AlertEngine, Notification, NotificationScheduler
from manny.reminders import ReminderCreate, ReminderStore
from manny.state import PrivacyState, RuntimeState, StateMachine


async def test_due_reminder_delivers_once_within_cooldown(tmp_path: Path) -> None:
    now = datetime(2026, 8, 8, 12, tzinfo=UTC)
    store = ReminderStore(tmp_path / "manny.sqlite3")
    await store.initialize()
    await store.create(ReminderCreate(title="Review card bill", due_at=now - timedelta(minutes=1)))
    state = StateMachine()
    await state.transition(
        RuntimeState.PRESENT,
        force=True,
        presence=True,
        people_count=1,
        privacy=PrivacyState.PRESENT_TRUSTED,
    )
    delivered: list[Notification] = []

    async def receive(notification: Notification) -> None:
        delivered.append(notification)

    scheduler = NotificationScheduler(store, AlertEngine(time(22), time(7)), state, receive)
    assert await scheduler.tick(now) is not None
    assert await scheduler.tick(now + timedelta(minutes=5)) is None
    assert len(delivered) == 1
