"""Low-frequency local presence monitor; no frames are persisted."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from manny.hardware.interfaces import CameraAdapter
from manny.state import StateMachine
from manny.vision.models import PresenceEvent

PresenceListener = Callable[[PresenceEvent], Awaitable[None]]


class VisionService:
    def __init__(
        self,
        camera: CameraAdapter,
        state: StateMachine,
        listener: PresenceListener,
        *,
        interval_seconds: float = 1.0,
    ) -> None:
        self._camera = camera
        self._state = state
        self._listener = listener
        self._interval = interval_seconds
        self._last_count: int | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def poll_once(self) -> PresenceEvent | None:
        count = max(0, await self._camera.people_count())
        if count == self._last_count:
            return None
        self._last_count = count
        event = PresenceEvent(present=count > 0, people_count=count)
        await self._state.set_presence(count)
        await self._listener(event)
        return event

    async def _run(self) -> None:
        while True:
            await self.poll_once()
            await asyncio.sleep(self._interval)
