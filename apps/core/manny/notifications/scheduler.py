from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from manny.notifications.engine import (
    AlertEngine,
    DeliveryDecision,
    Notification,
    Severity,
)
from manny.reminders import ReminderStore
from manny.state import StateMachine

NotificationListener = Callable[[Notification], Awaitable[None]]


class NotificationScheduler:
    def __init__(
        self,
        reminders: ReminderStore,
        engine: AlertEngine,
        state: StateMachine,
        listener: NotificationListener,
        *,
        interval_seconds: float = 30,
    ) -> None:
        self._reminders = reminders
        self._engine = engine
        self._state = state
        self._listener = listener
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def tick(self, now: datetime | None = None) -> Notification | None:
        current = now or datetime.now(UTC)
        due = [item for item in await self._reminders.list() if item.due_at <= current]
        for item in due:
            notification = Notification(
                event_id=f"reminder:{item.id}",
                title="Reminder",
                message=item.title,
                severity=Severity.REMINDER,
                first_seen=item.created_at,
                expires_at=item.due_at + timedelta(days=1),
                cooldown_seconds=3600,
            )
            decision = self._engine.decide(
                notification,
                now=current,
                present=self._state.snapshot.presence,
                privacy=self._state.snapshot.privacy,
            )
            if decision is DeliveryDecision.DELIVER:
                await self._listener(notification)
                return notification
        return None

    async def _run(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(self._interval)
