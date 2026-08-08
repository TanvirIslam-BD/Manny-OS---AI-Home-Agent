"""The single authoritative Manny runtime state machine."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from manny.state.models import PrivacyState, RuntimeSnapshot, RuntimeState

StateListener = Callable[[RuntimeSnapshot], Awaitable[None]]


class InvalidTransitionError(ValueError):
    pass


_FLOW: dict[RuntimeState, set[RuntimeState]] = {
    RuntimeState.BOOTING: {RuntimeState.PAIRING, RuntimeState.IDLE, RuntimeState.ERROR},
    RuntimeState.PAIRING: {RuntimeState.IDLE, RuntimeState.OFFLINE, RuntimeState.ERROR},
    RuntimeState.IDLE: {
        RuntimeState.PRESENT,
        RuntimeState.LISTENING,
        RuntimeState.DASHBOARD,
        RuntimeState.ALERT,
        RuntimeState.OFFLINE,
        RuntimeState.CAMERA_DISABLED,
        RuntimeState.MIC_MUTED,
        RuntimeState.ERROR,
    },
    RuntimeState.PRESENT: {
        RuntimeState.IDLE,
        RuntimeState.LISTENING,
        RuntimeState.DASHBOARD,
        RuntimeState.ALERT,
        RuntimeState.OFFLINE,
        RuntimeState.CAMERA_DISABLED,
        RuntimeState.MIC_MUTED,
        RuntimeState.ERROR,
    },
    RuntimeState.LISTENING: {
        RuntimeState.TRANSCRIBING,
        RuntimeState.IDLE,
        RuntimeState.PRESENT,
        RuntimeState.MIC_MUTED,
        RuntimeState.ERROR,
    },
    RuntimeState.TRANSCRIBING: {RuntimeState.THINKING, RuntimeState.ERROR},
    RuntimeState.THINKING: {
        RuntimeState.CONFIRMING,
        RuntimeState.SPEAKING,
        RuntimeState.DASHBOARD,
        RuntimeState.ERROR,
    },
    RuntimeState.CONFIRMING: {
        RuntimeState.SPEAKING,
        RuntimeState.IDLE,
        RuntimeState.PRESENT,
        RuntimeState.ERROR,
    },
    RuntimeState.SPEAKING: {RuntimeState.IDLE, RuntimeState.PRESENT, RuntimeState.ERROR},
    RuntimeState.DASHBOARD: {
        RuntimeState.IDLE,
        RuntimeState.PRESENT,
        RuntimeState.LISTENING,
        RuntimeState.ALERT,
        RuntimeState.OFFLINE,
        RuntimeState.ERROR,
    },
    RuntimeState.ALERT: {
        RuntimeState.IDLE,
        RuntimeState.PRESENT,
        RuntimeState.LISTENING,
        RuntimeState.DASHBOARD,
        RuntimeState.OFFLINE,
        RuntimeState.ERROR,
    },
    RuntimeState.OFFLINE: {
        RuntimeState.IDLE,
        RuntimeState.PRESENT,
        RuntimeState.DASHBOARD,
        RuntimeState.ERROR,
    },
    RuntimeState.CAMERA_DISABLED: {
        RuntimeState.IDLE,
        RuntimeState.LISTENING,
        RuntimeState.MIC_MUTED,
        RuntimeState.ERROR,
    },
    RuntimeState.MIC_MUTED: {
        RuntimeState.IDLE,
        RuntimeState.PRESENT,
        RuntimeState.CAMERA_DISABLED,
        RuntimeState.ERROR,
    },
    RuntimeState.ERROR: {RuntimeState.BOOTING, RuntimeState.IDLE},
}


class StateMachine:
    def __init__(self, initial: RuntimeSnapshot | None = None) -> None:
        self._snapshot = initial or RuntimeSnapshot()
        self._lock = asyncio.Lock()
        self._listeners: list[StateListener] = []

    @property
    def snapshot(self) -> RuntimeSnapshot:
        return self._snapshot

    def subscribe(self, listener: StateListener) -> None:
        self._listeners.append(listener)

    async def transition(
        self,
        target: RuntimeState,
        *,
        message: str | None = None,
        force: bool = False,
        **changes: object,
    ) -> RuntimeSnapshot:
        async with self._lock:
            current = self._snapshot.state
            if target != current and not force and target not in _FLOW[current]:
                raise InvalidTransitionError(f"cannot transition from {current} to {target}")
            update = {
                "state": target,
                "status_message": message or _default_message(target),
                "sequence": self._snapshot.sequence + 1,
                "updated_at": datetime.now(UTC),
                **changes,
            }
            self._snapshot = self._snapshot.model_copy(update=update)
            listeners = tuple(self._listeners)
        for listener in listeners:
            await listener(self._snapshot)
        return self._snapshot

    async def set_presence(self, people_count: int) -> RuntimeSnapshot:
        if not self._snapshot.camera_enabled:
            return self._snapshot

        people_count = max(0, people_count)
        present = people_count > 0
        if self._snapshot.privacy is PrivacyState.PRIVACY_LOCKED:
            privacy = PrivacyState.PRIVACY_LOCKED
        else:
            privacy = (
                PrivacyState.MULTIPLE_PEOPLE
                if people_count > 1
                else PrivacyState.PRESENT_UNKNOWN
                if present
                else PrivacyState.PRIVATE_IDLE
            )
        target = RuntimeState.PRESENT if present else RuntimeState.IDLE
        return await self.transition(
            target,
            message="Someone is nearby" if present else "Ready when you are",
            force=self._snapshot.state not in {RuntimeState.IDLE, RuntimeState.PRESENT},
            presence=present,
            people_count=people_count,
            privacy=privacy,
        )


def _default_message(state: RuntimeState) -> str:
    return {
        RuntimeState.BOOTING: "Starting Manny",
        RuntimeState.PAIRING: "Ready to pair",
        RuntimeState.IDLE: "Ready when you are",
        RuntimeState.PRESENT: "Welcome back",
        RuntimeState.LISTENING: "I'm listening",
        RuntimeState.TRANSCRIBING: "I heard you",
        RuntimeState.THINKING: "Working on that",
        RuntimeState.CONFIRMING: "Please confirm",
        RuntimeState.SPEAKING: "Here's what I found",
        RuntimeState.DASHBOARD: "Your money at a glance",
        RuntimeState.ALERT: "Something needs attention",
        RuntimeState.OFFLINE: "Using last synced information",
        RuntimeState.CAMERA_DISABLED: "Camera is off",
        RuntimeState.MIC_MUTED: "Microphone is muted",
        RuntimeState.ERROR: "Manny needs attention",
    }[state]
