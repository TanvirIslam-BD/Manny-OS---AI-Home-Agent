"""REST and WebSocket routes for the localhost display and simulator."""

from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from mcp.shared.auth import AuthorizationCodeResult
from pydantic import BaseModel, Field

from manny.agent import AgentQuery, AgentResponse
from manny.i18n import LANGUAGE_TAG_PATTERN
from manny.lifecycle import RuntimeServices
from manny.mcp import MCPStatus
from manny.reminders import Reminder, ReminderCreate
from manny.state import PrivacyState, RuntimeSnapshot, RuntimeState
from manny.voice import AudioBuffer, VoiceBusyError

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


class ListeningRequest(BaseModel):
    enabled: bool


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
    try:
        response = await services.agent.answer(body, privacy=services.state.snapshot.privacy)
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
        result = await services.voice.run_turn(
            AudioBuffer(pcm=body.text.encode(), language_hint=body.language),
            privacy=services.state.snapshot.privacy,
            authenticated=body.authenticated,
        )
    except VoiceBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return VoiceSimulationResponse(
        transcript=result.transcript.text,
        answer=result.answer,
        tool_name=result.tool_name,
        language=result.language,
    )


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
