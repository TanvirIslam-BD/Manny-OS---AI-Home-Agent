"""REST and WebSocket routes for the localhost display and simulator."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from mcp.shared.auth import AuthorizationCodeResult
from pydantic import BaseModel, Field

from manny.lifecycle import RuntimeServices
from manny.mcp import MCPStatus
from manny.state import PrivacyState, RuntimeSnapshot, RuntimeState

router = APIRouter()


class StateRequest(BaseModel):
    state: RuntimeState
    message: str | None = Field(default=None, max_length=160)


class PresenceRequest(BaseModel):
    people_count: int = Field(ge=0, le=8)


class ConnectivityRequest(BaseModel):
    connected: bool


def services_from_request(request: Request) -> RuntimeServices:
    return cast(RuntimeServices, request.app.state.services)


Services = Annotated[RuntimeServices, Depends(services_from_request)]


@router.get("/health")
async def get_health(services: Services) -> dict[str, object]:
    return services.health()


@router.get("/state", response_model=RuntimeSnapshot)
async def get_state(services: Services) -> RuntimeSnapshot:
    return services.state.snapshot


@router.get("/settings/public")
async def get_public_settings(services: Services) -> dict[str, object]:
    return services.settings.public_dict()


@router.get("/mcp/status", response_model=MCPStatus)
async def get_mcp_status(services: Services) -> MCPStatus:
    return services.mcp.status


@router.post("/mcp/connect", response_model=MCPStatus)
async def connect_mcp(services: Services) -> MCPStatus:
    return await services.mcp.begin_authorization()


@router.get("/mcp/oauth/callback")
async def mcp_oauth_callback(
    services: Services,
    code: str | None = None,
    state: str | None = None,
    iss: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
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


@router.post("/simulator/state", response_model=RuntimeSnapshot)
async def simulator_state(body: StateRequest, services: Services) -> RuntimeSnapshot:
    _require_simulator(services)
    return await services.state.transition(
        body.state,
        force=True,
        message=body.message,
        connected=body.state != RuntimeState.OFFLINE,
        camera_enabled=body.state != RuntimeState.CAMERA_DISABLED,
        microphone_muted=body.state == RuntimeState.MIC_MUTED,
    )


@router.post("/simulator/presence", response_model=RuntimeSnapshot)
async def simulator_presence(body: PresenceRequest, services: Services) -> RuntimeSnapshot:
    _require_simulator(services)
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
