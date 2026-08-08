"""Construction and lifecycle of dependency-injected runtime services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from manny.api.events import EventBus
from manny.config import Settings
from manny.hardware import HardwareBundle, LedState, build_mock_hardware
from manny.mcp import MCPConnectionPhase, MCPStatus, MockMCPClient, MoneyCopilotMCPClient
from manny.state import RuntimeSnapshot, RuntimeState, StateMachine


@dataclass(slots=True)
class RuntimeServices:
    settings: Settings
    state: StateMachine
    events: EventBus
    hardware: HardwareBundle
    mcp: MockMCPClient | MoneyCopilotMCPClient

    async def start(self) -> None:
        self.state.subscribe(self._on_state_change)
        await self.hardware.led.set_state(LedState.BOOTING)
        if self.settings.camera_enabled:
            await self.hardware.camera.start()
        await self.state.transition(
            RuntimeState.IDLE,
            message="Ready when you are",
            camera_enabled=self.settings.camera_enabled,
        )
        await self.mcp.start()

    async def stop(self) -> None:
        await self.mcp.stop()
        await self.hardware.camera.stop()

    async def _on_state_change(self, snapshot: RuntimeSnapshot) -> None:
        await self.hardware.led.set_state(_led_for_state(snapshot.state))
        await self.events.publish("system.state", snapshot.model_dump(mode="json"))

    async def _on_mcp_status(self, status: MCPStatus) -> None:
        snapshot = self.state.snapshot
        message = snapshot.status_message
        if snapshot.state in {RuntimeState.IDLE, RuntimeState.OFFLINE}:
            message = status.detail
        await self.state.transition(
            snapshot.state,
            force=True,
            message=message,
            connected=status.connected,
        )
        await self.events.publish("mcp.status", status.model_dump(mode="json"))

    def health(self) -> dict[str, Any]:
        phase = self.mcp.status.phase
        money_status = (
            "offline"
            if self.state.snapshot.state == RuntimeState.OFFLINE
            else "ok"
            if phase in {MCPConnectionPhase.CONNECTED, MCPConnectionPhase.MOCK}
            else phase.value
        )
        status = "ok" if money_status == "ok" else "degraded"
        return {
            "status": status,
            "components": {
                "database": "not_configured",
                "display": "ok",
                "microphone": "muted" if self.state.snapshot.microphone_muted else "ok",
                "speaker": "ok",
                "camera": "ok" if self.state.snapshot.camera_enabled else "disabled",
                "llm": "mock",
                "money_mcp": money_status,
            },
        }


def build_services(settings: Settings) -> RuntimeServices:
    if settings.hardware_mode != "mock":
        raise RuntimeError("real hardware adapters are introduced in Phase 7")
    mcp = (
        MoneyCopilotMCPClient(settings)
        if settings.mcp_mode == "remote_http"
        else MockMCPClient()
    )
    services = RuntimeServices(
        settings=settings,
        state=StateMachine(
            RuntimeSnapshot(camera_enabled=settings.camera_enabled)
        ),
        events=EventBus(),
        hardware=build_mock_hardware(camera_enabled=settings.camera_enabled),
        mcp=mcp,
    )
    mcp.set_listener(services._on_mcp_status)
    return services


def _led_for_state(state: RuntimeState) -> LedState:
    return {
        RuntimeState.BOOTING: LedState.BOOTING,
        RuntimeState.PAIRING: LedState.READY,
        RuntimeState.IDLE: LedState.READY,
        RuntimeState.PRESENT: LedState.READY,
        RuntimeState.LISTENING: LedState.LISTENING,
        RuntimeState.TRANSCRIBING: LedState.THINKING,
        RuntimeState.THINKING: LedState.THINKING,
        RuntimeState.CONFIRMING: LedState.WARNING,
        RuntimeState.SPEAKING: LedState.SPEAKING,
        RuntimeState.DASHBOARD: LedState.READY,
        RuntimeState.ALERT: LedState.WARNING,
        RuntimeState.OFFLINE: LedState.OFFLINE,
        RuntimeState.CAMERA_DISABLED: LedState.WARNING,
        RuntimeState.MIC_MUTED: LedState.MUTED,
        RuntimeState.ERROR: LedState.ERROR,
    }[state]
