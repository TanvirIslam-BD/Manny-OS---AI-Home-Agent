"""Mock MCP connection used by tests and Phase 0 simulator mode."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from mcp.shared.auth import AuthorizationCodeResult

from manny.mcp.models import MCPConnectionPhase, MCPStatus

StatusListener = Callable[[MCPStatus], Awaitable[None]]


class MockMCPClient:
    def __init__(self, listener: StatusListener | None = None) -> None:
        self._listener = listener
        self._status = MCPStatus(
            phase=MCPConnectionPhase.MOCK,
            connected=True,
            protocol_version="mock",
            detail="Using simulator finance fixtures",
        )

    @property
    def status(self) -> MCPStatus:
        return self._status

    def set_listener(self, listener: StatusListener) -> None:
        self._listener = listener

    async def start(self) -> None:
        if self._listener:
            await self._listener(self._status)

    async def stop(self) -> None:
        return None

    async def begin_authorization(self) -> MCPStatus:
        return self._status

    async def complete_authorization(self, _result: AuthorizationCodeResult) -> MCPStatus:
        return self._status

    async def fail_authorization(self, _detail: str) -> MCPStatus:
        return self._status
