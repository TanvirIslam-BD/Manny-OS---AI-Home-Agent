"""Construction and lifecycle of dependency-injected runtime services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any

from manny.agent import OllamaAgentModel, RuleBasedAgent, ToolBroker
from manny.api.events import EventBus
from manny.config import Settings
from manny.hardware import HardwareBundle, LedState, build_mock_hardware, build_real_hardware
from manny.i18n import normalize_language_tag
from manny.mcp import MCPConnectionPhase, MCPStatus, MockMCPClient, MoneyCopilotMCPClient
from manny.memory import MemoryStats, MemoryStore
from manny.notifications import AlertEngine, Notification, NotificationScheduler
from manny.observability import MetricsRegistry
from manny.policy import PolicyEngine
from manny.reminders import ReminderStore
from manny.security import PasscodeLock
from manny.state import PrivacyState, RuntimeSnapshot, RuntimeState, StateMachine
from manny.storage import FinanceCache
from manny.vision import PresenceEvent, VisionService, build_vision_language_model
from manny.voice import (
    EnergyVoiceActivity,
    EspeakTextToSpeech,
    HalfDuplexVoiceCoordinator,
    KokoroTextToSpeech,
    MockSpeechToText,
    MockTextToSpeech,
    MockVoiceActivity,
    MoonshineSpeechToText,
    PhraseWakeWord,
    SpeechToText,
    TextToSpeech,
    UtteranceRecorder,
    VoiceActivityDetector,
    VoiceLoop,
    WhisperCppSpeechToText,
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
    voice_loop: VoiceLoop | None
    finance_cache: FinanceCache
    memory: MemoryStore
    security: PasscodeLock
    vision: VisionService
    reminders: ReminderStore
    alerts: AlertEngine
    scheduler: NotificationScheduler
    metrics: MetricsRegistry
    camera_active: bool = True

    async def start(self) -> None:
        self.state.subscribe(self._on_state_change)
        await self.hardware.led.set_state(LedState.BOOTING)
        self.camera_active = self.settings.camera_enabled
        if self.settings.camera_enabled:
            await self.hardware.camera.start()
        await self.state.transition(
            RuntimeState.IDLE,
            message="Ready when you are",
            camera_enabled=self.settings.camera_enabled,
        )
        await self.mcp.start()
        await self.finance_cache.initialize()
        await self.memory.initialize()
        await self.agent.hydrate()
        await self.reminders.initialize()
        await self.scheduler.start()
        if self.settings.camera_enabled:
            await self.vision.start()
        if self.voice_loop is not None:
            await self.voice_loop.start()
        await self.state.transition(
            self.state.snapshot.state,
            force=True,
            message=self.state.snapshot.status_message,
            listening_enabled=self.voice_loop is not None,
            listening_available=self.voice_loop is not None,
            language=self.settings.voice_default_language,
        )

    async def set_language(self, language: str) -> RuntimeSnapshot:
        """Change the spoken/recognition language for the whole device."""

        resolved = "auto" if language.casefold() == "auto" else normalize_language_tag(language)
        if self.voice_loop is not None:
            self.voice_loop.set_language(resolved)
        return await self.state.transition(
            self.state.snapshot.state,
            force=True,
            message=self.state.snapshot.status_message,
            language=resolved,
        )

    async def set_listening(self, enabled: bool) -> RuntimeSnapshot:
        """Start or stop the device listen loop without restarting the service."""

        if self.voice_loop is None:
            return self.state.snapshot
        if enabled:
            await self.voice_loop.start()
        else:
            await self.voice_loop.stop()
        return await self.state.transition(
            self.state.snapshot.state,
            force=True,
            message="Always listening is on" if enabled else "Always listening is off",
            listening_enabled=enabled,
        )

    async def stop(self) -> None:
        if self.voice_loop is not None:
            await self.voice_loop.stop()
        await self.mcp.stop()
        await self.vision.stop()
        await self.scheduler.stop()
        await self.hardware.camera.stop()

    async def _on_state_change(self, snapshot: RuntimeSnapshot) -> None:
        # Disabling the camera previously flipped a flag and left the adapter
        # running, so the lens stayed open. Enforce it at the hardware boundary:
        # a stopped camera cannot hand a frame to anything, whatever asks.
        if snapshot.camera_enabled != self.camera_active:
            if snapshot.camera_enabled:
                await self.hardware.camera.start()
            else:
                await self.hardware.camera.stop()
            self.camera_active = snapshot.camera_enabled
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

    async def apply_unlock_state(self) -> RuntimeSnapshot:
        """Reflect the unlock session in privacy state.

        PRESENT_TRUSTED had no producer before this: presence alone can only say
        that somebody is there, never that they are the account holder. A verified
        passcode is what promotes the session, which is also what lets private
        reminders be delivered at all.
        """
        snapshot = self.state.snapshot
        if self.security.is_unlocked():
            privacy = PrivacyState.PRESENT_TRUSTED
        elif snapshot.people_count > 1:
            privacy = PrivacyState.MULTIPLE_PEOPLE
        elif snapshot.presence:
            privacy = PrivacyState.PRESENT_UNKNOWN
        else:
            privacy = PrivacyState.PRIVATE_IDLE
        return await self.state.transition(
            snapshot.state,
            force=True,
            message=snapshot.status_message,
            privacy=privacy,
        )

    async def announce_reminder(self, response: object) -> None:
        """Publish reminders created through conversation.

        The REST route already broadcasts; without this the Alerts screen only
        learns about a spoken reminder on its next full reload.
        """
        data = getattr(response, "data", None)
        if getattr(response, "intent", None) != "create_reminder" or not isinstance(data, dict):
            return
        await self.events.publish("notification.created", data)

    async def memory_stats(self) -> MemoryStats:
        return await self.memory.stats()

    async def clear_memory(self) -> MemoryStats:
        await self.agent.forget()
        await self.metrics.increment("memory_clears")
        return await self.memory.stats()

    async def factory_reset(self) -> None:
        await self.mcp.reset_credentials()
        await self.finance_cache.clear()
        await self.agent.forget()
        await self.security.clear()
        await self.reminders.clear()
        await self.metrics.increment("device_resets")
        await self.state.transition(
            RuntimeState.PAIRING,
            force=True,
            message="Device reset complete. Pair Money Copilot to continue.",
            privacy=PrivacyState.PRIVACY_LOCKED,
        )

    async def switch_mcp_account(self) -> MCPStatus:
        """Remove account-specific state and begin a fresh MCP authorization."""
        await self.mcp.reset_credentials()
        await self.finance_cache.clear()
        await self.agent.clear_context()
        await self.metrics.increment("mcp_account_switches")
        return await self.mcp.begin_authorization()

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
    memory = MemoryStore(settings.data_directory / "memory.sqlite3")
    security = PasscodeLock(settings.data_directory / "passcode.json")
    reminders = ReminderStore(settings.data_directory / "manny.sqlite3")
    alerts = AlertEngine(
        time.fromisoformat(settings.quiet_hours_start),
        time.fromisoformat(settings.quiet_hours_end),
    )
    model = (
        OllamaAgentModel(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
        )
        if settings.llm_backend == "ollama"
        else None
    )
    hardware = (
        build_real_hardware(settings)
        if settings.hardware_mode == "real"
        else build_mock_hardware(camera_enabled=settings.camera_enabled)
    )
    agent = RuleBasedAgent(
        ToolBroker(mcp, PolicyEngine(), finance_cache),
        remote=settings.mcp_mode == "remote_http",
        model=model,
        max_context_turns=settings.llm_context_turns,
        timezone=settings.user_timezone,
        memory=memory,
        reminders=reminders,
        camera=hardware.camera,
        vision_model=build_vision_language_model(
            settings.vision_language_backend,
            base_url=settings.vision_language_base_url,
            model=settings.vision_language_model,
            timeout_seconds=settings.vision_language_timeout_seconds,
        ),
    )
    stt: SpeechToText
    if settings.stt_backend == "whisper_cpp":
        stt = WhisperCppSpeechToText(
            binary=settings.whisper_cpp_binary,
            model=settings.whisper_cpp_model,
            threads=settings.whisper_cpp_threads,
            timeout_seconds=settings.whisper_cpp_timeout_seconds,
            default_language=settings.voice_default_language,
        )
    elif settings.stt_backend == "moonshine":
        stt = MoonshineSpeechToText()
    else:
        stt = MockSpeechToText()
    tts: TextToSpeech
    if settings.tts_backend == "espeak_ng":
        tts = EspeakTextToSpeech(settings.espeak_ng_binary)
    elif settings.tts_backend == "kokoro":
        tts = KokoroTextToSpeech()
    else:
        tts = MockTextToSpeech()
    events = EventBus()
    vad: VoiceActivityDetector = (
        EnergyVoiceActivity(threshold=settings.voice_vad_threshold)
        if settings.hardware_mode == "real"
        else MockVoiceActivity()
    )
    voice = HalfDuplexVoiceCoordinator(
        stt=stt,
        tts=tts,
        vad=vad,
        agent=agent,
        state=state,
        speaker=hardware.audio_output,
        voice=settings.tts_voice,
        stream_replies=settings.llm_stream_replies,
    )
    services = RuntimeServices(
        settings=settings,
        state=state,
        events=events,
        hardware=hardware,
        mcp=mcp,
        agent=agent,
        voice=voice,
        voice_loop=(
            VoiceLoop(
                hardware.audio_input,
                voice,
                state,
                chunk_seconds=settings.voice_capture_seconds,
                language=settings.voice_default_language,
                wake_word=(
                    PhraseWakeWord(stt, phrases=settings.wake_phrases)
                    if settings.wake_word_enabled
                    else None
                ),
                follow_up_seconds=settings.wake_follow_up_seconds,
                # Same detector the coordinator uses, so a silent chunk is rejected
                # before recognition rather than after it.
                vad=vad,
                recorder=(
                    UtteranceRecorder(
                        # Frames are far shorter than the detector's default duration
                        # floor, which would reject every one of them.
                        EnergyVoiceActivity(
                            threshold=settings.voice_vad_threshold, minimum_seconds=0.0
                        ),
                        silence_hold_seconds=settings.voice_silence_hold_seconds,
                        max_utterance_seconds=settings.voice_max_utterance_seconds,
                    )
                    if settings.voice_endpointing_enabled
                    else None
                ),
                frame_seconds=settings.voice_frame_seconds,
            )
            if settings.voice_loop_active
            else None
        ),
        finance_cache=finance_cache,
        memory=memory,
        security=security,
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
