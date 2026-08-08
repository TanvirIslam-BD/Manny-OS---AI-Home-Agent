"""Construction and lifecycle of dependency-injected runtime services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any

from manny.agent import LlamaCppAgentModel, RuleBasedAgent, ToolBroker
from manny.api.events import EventBus
from manny.config import Settings
from manny.hardware import HardwareBundle, LedState, build_mock_hardware, build_real_hardware
from manny.mcp import MCPConnectionPhase, MCPStatus, MockMCPClient, MoneyCopilotMCPClient
from manny.notifications import AlertEngine, Notification, NotificationScheduler
from manny.observability import MetricsRegistry
from manny.policy import PolicyEngine
from manny.reminders import ReminderStore
from manny.state import PrivacyState, RuntimeSnapshot, RuntimeState, StateMachine
from manny.storage import FinanceCache
from manny.vision import PresenceEvent, VisionService
from manny.voice import (
    HalfDuplexVoiceCoordinator,
    KokoroTextToSpeech,
    MockSpeechToText,
    MockTextToSpeech,
    MockVoiceActivity,
    MoonshineSpeechToText,
)


@dataclass(slots=True)
class RuntimeServices:
    settings: Settings
    state: StateMachine
    events: EventBus
    hardware: HardwareBundle
    mcp: MockMCPClient | MoneyCopilotMCPClient
    agent: RuleBasedAgent
    voice: HalfDuplexVoiceCoordinator
    finance_cache: FinanceCache
    vision: VisionService
    reminders: ReminderStore
    alerts: AlertEngine
    scheduler: NotificationScheduler
    metrics: MetricsRegistry

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
        await self.finance_cache.initialize()
        await self.reminders.initialize()
        await self.scheduler.start()
        if self.settings.camera_enabled:
            await self.vision.start()

    async def stop(self) -> None:
        await self.mcp.stop()
        await self.vision.stop()
        await self.scheduler.stop()
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

    async def factory_reset(self) -> None:
        await self.mcp.reset_credentials()
        await self.finance_cache.clear()
        await self.reminders.clear()
        await self.metrics.increment("device_resets")
        await self.state.transition(
            RuntimeState.PAIRING,
            force=True,
            message="Device reset complete. Pair Money Copilot to continue.",
            privacy=PrivacyState.PRIVACY_LOCKED,
        )

    async def _on_presence(self, event: PresenceEvent) -> None:
        await self.events.publish("presence.changed", event.model_dump(mode="json"))

    async def _on_notification(self, notification: Notification) -> None:
        await self.state.transition(
            RuntimeState.ALERT, force=True, message=notification.message[:160]
        )
        await self.events.publish("notification.created", notification.model_dump(mode="json"))

    def health(self) -> dict[str, Any]:
        phase = self.mcp.status.phase
        money_status = (
            "offline"
            if self.state.snapshot.state == RuntimeState.OFFLINE
            else "ok"
            if phase in {MCPConnectionPhase.CONNECTED, MCPConnectionPhase.MOCK}
            else phase.value
        )
        llm_status = self.agent.model_status
        status = (
            "ok"
            if money_status == "ok" and llm_status in {"mock", "ok", "not_checked"}
            else "degraded"
        )
        return {
            "status": status,
            "components": {
                "database": "ok",
                "display": "ok",
                "microphone": "muted" if self.state.snapshot.microphone_muted else "ok",
                "speaker": "ok",
                "camera": "ok" if self.state.snapshot.camera_enabled else "disabled",
                "llm": llm_status,
                "money_mcp": money_status,
            },
        }


def build_services(settings: Settings) -> RuntimeServices:
    mcp = MoneyCopilotMCPClient(settings) if settings.mcp_mode == "remote_http" else MockMCPClient()
    state = StateMachine(RuntimeSnapshot(camera_enabled=settings.camera_enabled))
    finance_cache = FinanceCache(settings.data_directory / "finance_cache.sqlite3")
    reminders = ReminderStore(settings.data_directory / "manny.sqlite3")
    alerts = AlertEngine(
        time.fromisoformat(settings.quiet_hours_start),
        time.fromisoformat(settings.quiet_hours_end),
    )
    model = (
        LlamaCppAgentModel(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
        )
        if settings.llm_backend == "llama_cpp"
        else None
    )
    agent = RuleBasedAgent(
        ToolBroker(mcp, PolicyEngine(), finance_cache),
        remote=settings.mcp_mode == "remote_http",
        model=model,
        max_context_turns=settings.llm_context_turns,
    )
    stt = MoonshineSpeechToText() if settings.stt_backend == "moonshine" else MockSpeechToText()
    tts = KokoroTextToSpeech() if settings.tts_backend == "kokoro" else MockTextToSpeech()
    events = EventBus()
    hardware = (
        build_real_hardware(settings)
        if settings.hardware_mode == "real"
        else build_mock_hardware(camera_enabled=settings.camera_enabled)
    )
    services = RuntimeServices(
        settings=settings,
        state=state,
        events=events,
        hardware=hardware,
        mcp=mcp,
        agent=agent,
        voice=HalfDuplexVoiceCoordinator(
            stt=stt,
            tts=tts,
            vad=MockVoiceActivity(),
            agent=agent,
            state=state,
        ),
        finance_cache=finance_cache,
        vision=VisionService(
            hardware.camera,
            state,
            lambda event: events.publish("presence.changed", event.model_dump(mode="json")),
        ),
        reminders=reminders,
        alerts=alerts,
        scheduler=NotificationScheduler(
            reminders,
            alerts,
            state,
            lambda notification: _deliver_notification(state, events, notification),
        ),
        metrics=MetricsRegistry(),
    )
    mcp.set_listener(services._on_mcp_status)
    return services


async def _deliver_notification(
    state: StateMachine, events: EventBus, notification: Notification
) -> None:
    await state.transition(RuntimeState.ALERT, force=True, message=notification.message[:160])
    await events.publish("notification.created", notification.model_dump(mode="json"))


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
