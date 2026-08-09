"""REST and WebSocket routes for the localhost display and simulator."""

from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import RedirectResponse
from mcp.shared.auth import AuthorizationCodeResult
from pydantic import BaseModel, Field

from manny.agent import AgentQuery, AgentResponse
from manny.i18n import LANGUAGE_TAG_PATTERN, detect_text_language
from manny.lifecycle import RuntimeServices
from manny.mcp import MCPStatus
from manny.memory import MemoryStats
from manny.reminders import Reminder, ReminderCreate
from manny.security import LockedOutError, PasscodeError, SecurityStatus
from manny.state import PrivacyState, RuntimeSnapshot, RuntimeState
from manny.voice import VoiceBusyError

router = APIRouter()


class StateRequest(BaseModel):
    state: RuntimeState
    message: str | None = Field(default=None, max_length=160)


class PresenceRequest(BaseModel):
    people_count: int = Field(ge=0, le=8)


class ConnectivityRequest(BaseModel):
    connected: bool


class VoiceSimulationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    authenticated: bool = False
    language: str | None = Field(
        default=None,
        min_length=2,
        max_length=35,
        pattern=rf"^(?:auto|{LANGUAGE_TAG_PATTERN.pattern[1:-1]})$",
    )


class VoiceSimulationResponse(BaseModel):
    transcript: str
    answer: str
    tool_name: str | None = None
    language: str = "en"


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    language: str = Field(
        default="en",
        min_length=2,
        max_length=35,
        pattern=rf"^(?:auto|{LANGUAGE_TAG_PATTERN.pattern[1:-1]})$",
    )


class ListeningRequest(BaseModel):
    enabled: bool


class LanguageRequest(BaseModel):
    language: str = Field(
        min_length=2,
        max_length=35,
        pattern=rf"^(?:auto|{LANGUAGE_TAG_PATTERN.pattern[1:-1]})$",
    )


class PasscodeRequest(BaseModel):
    passcode: str = Field(min_length=4, max_length=12)
    current_passcode: str | None = Field(default=None, min_length=4, max_length=12)


class BrightnessRequest(BaseModel):
    value: float = Field(ge=0, le=1)


class UnlockRequest(BaseModel):
    passcode: str = Field(min_length=4, max_length=12)


class DeviceResetRequest(BaseModel):
    confirmation: Literal["RESET MANNY"]


def services_from_request(request: Request) -> RuntimeServices:
    return cast(RuntimeServices, request.app.state.services)


Services = Annotated[RuntimeServices, Depends(services_from_request)]


@router.get("/health")
async def get_health(services: Services) -> dict[str, object]:
    return services.health()


@router.get("/metrics")
async def get_metrics(services: Services) -> dict[str, int]:
    return services.metrics.snapshot()


@router.get("/state", response_model=RuntimeSnapshot)
async def get_state(services: Services) -> RuntimeSnapshot:
    return services.state.snapshot


@router.get("/settings/public")
async def get_public_settings(services: Services) -> dict[str, object]:
    return services.settings.public_dict()


@router.get("/mcp/status", response_model=MCPStatus)
async def get_mcp_status(services: Services) -> MCPStatus:
    return services.mcp.status


@router.post("/agent/query", response_model=AgentResponse)
async def agent_query(body: AgentQuery, services: Services) -> AgentResponse:
    await services.state.transition(
        RuntimeState.THINKING, force=True, message="Checking Money Copilot"
    )
    # Publish each sentence as the model produces it. Streaming already existed but
    # only the voice coordinator ever passed a listener, so a typed question waited
    # for the whole reply — measurably the worst case in the product, since decode
    # runs at 16 tok/s on a desktop CPU and half that on the device. The wait is
    # unchanged; what changes is that the user reads the first sentence while the
    # rest is still being generated.
    spoken_any = False
    # The reply's own language field arrives after the reply text does, so a sentence
    # has to be tagged with the language of the question — the same rule and the same
    # reason the voice coordinator uses the transcript's language when it speaks a
    # piece early. Without it the client cannot choose a voice until the reply is
    # over, which is exactly the wait streaming exists to remove.
    chunk_language = detect_text_language(body.text, body.language)

    async def publish_chunk(piece: str) -> None:
        nonlocal spoken_any
        if not spoken_any:
            # Same rule the coordinator follows: the face stops thinking once there
            # is something to say, rather than at the end of the whole reply.
            spoken_any = True
            await services.state.transition(
                RuntimeState.SPEAKING, force=True, message=piece[:160]
            )
        await services.events.publish(
            "agent.reply_chunk", {"text": piece, "language": chunk_language}
        )

    try:
        # `authenticated` from the caller is advisory only. Anything able to reach
        # the loopback API could set it, so the verified unlock session decides.
        query = body.model_copy(update={"authenticated": services.security.is_unlocked()})
        response = await services.agent.answer(
            query,
            privacy=services.state.snapshot.privacy,
            # Only a general-intent reply comes from the model. Finance answers are
            # built from validated MCP data and arrive whole in milliseconds, so
            # there is nothing to stream and nothing to gain.
            on_reply_chunk=publish_chunk if services.settings.llm_stream_replies else None,
        )
    except RuntimeError as exc:
        await services.state.transition(
            RuntimeState.ERROR, force=True, message="I couldn't validate that financial data"
        )
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except ValueError:
        await services.state.transition(
            RuntimeState.ERROR, force=True, message="I couldn't validate that financial data"
        )
        raise HTTPException(status_code=502, detail="Money Copilot returned invalid data") from None
    target = (
        RuntimeState.CONFIRMING
        if response.requires_confirmation or response.requires_authentication
        else RuntimeState.SPEAKING
    )
    await services.state.transition(target, force=True, message=response.answer[:160])
    await services.announce_reminder(response)
    return response


@router.post("/mcp/connect", response_model=MCPStatus)
async def connect_mcp(services: Services) -> MCPStatus:
    return await services.mcp.begin_authorization()


@router.post("/mcp/switch-account", response_model=MCPStatus)
async def switch_mcp_account(services: Services) -> MCPStatus:
    return await services.switch_mcp_account()


@router.get("/mcp/oauth/callback")
async def mcp_oauth_callback(
    services: Services,
    code: str | None = None,
    state: str | None = None,
    iss: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if services.mcp.status.connected:
        return RedirectResponse(url="/?mcp=connected", status_code=303)
    if error or not code:
        await services.mcp.fail_authorization("Money Copilot authorization was cancelled")
        return RedirectResponse(url="/?mcp=error", status_code=303)
    status = await services.mcp.complete_authorization(
        AuthorizationCodeResult(code=code, state=state, iss=iss)
    )
    outcome = "connected" if status.connected else "error"
    return RedirectResponse(url=f"/?mcp={outcome}", status_code=303)


@router.post("/interaction/push-to-talk", response_model=RuntimeSnapshot)
async def push_to_talk(services: Services) -> RuntimeSnapshot:
    if services.state.snapshot.microphone_muted:
        raise HTTPException(status_code=409, detail="microphone is muted")
    return await services.state.transition(RuntimeState.LISTENING, force=True)


@router.post("/interaction/voice/simulate", response_model=VoiceSimulationResponse)
async def simulate_voice(
    body: VoiceSimulationRequest, services: Services
) -> VoiceSimulationResponse:
    if services.state.snapshot.microphone_muted:
        raise HTTPException(status_code=409, detail="microphone is muted")
    try:
        # Text in, spoken reply out. Wrapping it in an AudioBuffer and running the
        # recognition stages over it only worked against the mock recogniser; the
        # device's energy voice activity rejected the same payload as silence.
        result = await services.voice.run_text_turn(
            body.text,
            privacy=services.state.snapshot.privacy,
            authenticated=services.security.is_unlocked(),
            language=body.language,
        )
    except VoiceBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    await services.announce_reminder(result)
    return VoiceSimulationResponse(
        transcript=result.transcript.text,
        answer=result.answer,
        tool_name=result.tool_name,
        language=result.language,
    )


@router.post(
    "/voice/speak",
    responses={200: {"content": {"audio/wav": {}}, "description": "Synthesised speech"}},
)
async def speak_reply(body: SpeechRequest, services: Services) -> Response:
    """Say a reply the browser has no voice for.

    Browser speech synthesis can only use voices the host operating system
    installed, and a default Windows install has none outside English, so Bengali
    and Hindi replies were shown and never spoken. This hands the same text to the
    adapter the device speaks with, which covers far more languages than any
    desktop voice set.

    It refuses rather than degrades. The mock backend returns the text itself as
    the audio payload, so serving that as a WAV would produce noise dressed up as
    speech — the fabricated-output failure the honest-degradation invariant
    forbids. No text is stored or logged: it is synthesised and streamed back.
    """
    if services.settings.tts_backend == "mock":
        raise HTTPException(
            status_code=503,
            detail="This device has no local speech synthesis configured.",
        )
    try:
        audio = await services.voice.synthesize(body.text, language=body.language)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail="Local speech synthesis is configured but did not answer.",
        ) from None
    return Response(content=audio.to_wav(), media_type="audio/wav")


@router.post("/interaction/cancel", response_model=RuntimeSnapshot)
async def cancel_interaction(services: Services) -> RuntimeSnapshot:
    target = RuntimeState.PRESENT if services.state.snapshot.presence else RuntimeState.IDLE
    return await services.state.transition(target, force=True)


@router.post("/privacy/lock", response_model=RuntimeSnapshot)
async def privacy_lock(services: Services) -> RuntimeSnapshot:
    return await services.state.transition(
        RuntimeState.IDLE,
        force=True,
        message="Privacy locked",
        privacy=PrivacyState.PRIVACY_LOCKED,
    )


@router.post("/device/listening", response_model=RuntimeSnapshot)
async def set_listening(body: ListeningRequest, services: Services) -> RuntimeSnapshot:
    if not services.state.snapshot.listening_available:
        raise HTTPException(status_code=409, detail="the device listen loop is unavailable")
    return await services.set_listening(body.enabled)


@router.post("/device/language", response_model=RuntimeSnapshot)
async def set_language(body: LanguageRequest, services: Services) -> RuntimeSnapshot:
    return await services.set_language(body.language)


@router.post("/device/brightness")
async def set_brightness(body: BrightnessRequest, services: Services) -> dict[str, float]:
    """Drive the display adapter, which until now had no caller."""
    try:
        await services.hardware.display.set_brightness(body.value)
    except OSError as exc:
        raise HTTPException(status_code=503, detail="the display is not adjustable") from exc
    return {"brightness": body.value}


@router.get("/security", response_model=SecurityStatus)
async def get_security(services: Services) -> SecurityStatus:
    return await services.security.status()


@router.post("/security/passcode", response_model=SecurityStatus)
async def set_passcode(body: PasscodeRequest, services: Services) -> SecurityStatus:
    try:
        status = await services.security.set_passcode(body.passcode, body.current_passcode)
    except PasscodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    await services.apply_unlock_state()
    return status


@router.post("/security/unlock", response_model=SecurityStatus)
async def unlock_device(body: UnlockRequest, services: Services) -> SecurityStatus:
    try:
        status = await services.security.unlock(body.passcode)
    except LockedOutError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None
    except PasscodeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None
    await services.apply_unlock_state()
    return status


@router.post("/security/lock", response_model=SecurityStatus)
async def lock_device(services: Services) -> SecurityStatus:
    status = await services.security.lock()
    await services.apply_unlock_state()
    return status


@router.get("/memory", response_model=MemoryStats)
async def get_memory(services: Services) -> MemoryStats:
    return await services.memory_stats()


@router.post("/memory/clear", response_model=MemoryStats)
async def clear_memory(services: Services) -> MemoryStats:
    return await services.clear_memory()


@router.post("/device/reset", response_model=RuntimeSnapshot)
async def reset_device(body: DeviceResetRequest, services: Services) -> RuntimeSnapshot:
    del body
    await services.factory_reset()
    return services.state.snapshot


@router.get("/reminders", response_model=list[Reminder])
async def list_reminders(services: Services) -> list[Reminder]:
    return await services.reminders.list()


@router.post("/reminders", response_model=Reminder, status_code=201)
async def create_reminder(body: ReminderCreate, services: Services) -> Reminder:
    reminder = await services.reminders.create(body)
    await services.events.publish("notification.created", reminder.model_dump(mode="json"))
    return reminder


@router.post("/reminders/{reminder_id}/complete", status_code=204)
async def complete_reminder(reminder_id: str, services: Services) -> None:
    if not await services.reminders.complete(reminder_id):
        raise HTTPException(status_code=404, detail="reminder not found")


@router.post("/simulator/state", response_model=RuntimeSnapshot)
async def simulator_state(body: StateRequest, services: Services) -> RuntimeSnapshot:
    _require_simulator(services)
    camera_disabled = body.state == RuntimeState.CAMERA_DISABLED
    return await services.state.transition(
        body.state,
        force=True,
        message=body.message,
        connected=body.state != RuntimeState.OFFLINE,
        camera_enabled=not camera_disabled,
        microphone_muted=body.state == RuntimeState.MIC_MUTED,
        **({"presence": False, "people_count": 0} if camera_disabled else {}),
    )


@router.post("/simulator/presence", response_model=RuntimeSnapshot)
async def simulator_presence(body: PresenceRequest, services: Services) -> RuntimeSnapshot:
    _require_simulator(services)
    if not services.state.snapshot.camera_enabled:
        raise HTTPException(status_code=409, detail="camera is disabled")
    camera = services.hardware.camera
    if hasattr(camera, "simulated_people_count"):
        camera.simulated_people_count = body.people_count
    return await services.state.set_presence(body.people_count)


@router.post("/simulator/connectivity", response_model=RuntimeSnapshot)
async def simulator_connectivity(body: ConnectivityRequest, services: Services) -> RuntimeSnapshot:
    _require_simulator(services)
    if not body.connected:
        return await services.state.transition(
            RuntimeState.OFFLINE,
            force=True,
            connected=False,
        )
    target = RuntimeState.PRESENT if services.state.snapshot.presence else RuntimeState.IDLE
    return await services.state.transition(
        target,
        force=True,
        message="Back online",
        connected=True,
    )


@router.websocket("/ws")
async def websocket_events(websocket: WebSocket) -> None:
    services: RuntimeServices = websocket.app.state.services
    await services.events.connect(websocket)
    await websocket.send_json(
        {"type": "system.state", "payload": services.state.snapshot.model_dump(mode="json")}
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await services.events.disconnect(websocket)


def _require_simulator(services: RuntimeServices) -> None:
    if services.settings.environment not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="simulator controls are disabled")
