from datetime import UTC, datetime, timedelta
from pathlib import Path

from manny.reminders import ReminderCreate, ReminderStore


async def test_reminders_are_persistent_and_completable(tmp_path: Path) -> None:
    path = tmp_path / "manny.sqlite3"
    store = ReminderStore(path)
    await store.initialize()
    created = await store.create(
        ReminderCreate(title="Review card bill", due_at=datetime.now(UTC) + timedelta(days=1))
    )

    reopened = ReminderStore(path)
    await reopened.initialize()
    assert [item.id for item in await reopened.list()] == [created.id]
    assert await reopened.complete(created.id) is True
    assert await reopened.list() == []
