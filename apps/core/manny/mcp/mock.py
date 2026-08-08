"""Mock MCP connection used by tests and Phase 0 simulator mode."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from mcp.shared.auth import AuthorizationCodeResult
from mcp_types import CallToolResult, TextContent

from manny.mcp.models import MCPConnectionPhase, MCPStatus

StatusListener = Callable[[MCPStatus], Awaitable[None]]


class MockMCPClient:
    TOOLS = [
        "money.get_budget_summary",
        "money.get_category_spending",
        "money.get_transactions",
        "money.get_budget_alerts",
        "money.get_recurring_payments",
    ]

    def __init__(self, listener: StatusListener | None = None) -> None:
        self._listener = listener
        self._status = MCPStatus(
            phase=MCPConnectionPhase.MOCK,
            connected=True,
            protocol_version="mock",
            discovered_tools=self.TOOLS,
            allowed_tools=self.TOOLS,
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

    async def reset_credentials(self) -> None:
        return None

    async def begin_authorization(self) -> MCPStatus:
        return self._status

    async def complete_authorization(self, _result: AuthorizationCodeResult) -> MCPStatus:
        return self._status

    async def fail_authorization(self, _detail: str) -> MCPStatus:
        return self._status

    async def call_tool(self, name: str, arguments: dict[str, object]) -> CallToolResult:
        now = datetime.now(UTC)
        fixtures: dict[str, object] = {
            "money.get_budget_summary": {
                "currency": "USD",
                "budget": 1800,
                "spent": 1240,
                "remaining": 560,
                "percent_used": 68.9,
                "as_of": now.isoformat(),
            },
            "money.get_category_spending": {
                "currency": "USD",
                "categories": [
                    {"name": "Dining", "amount": 458},
                    {"name": "Transport", "amount": 220},
                ],
                "as_of": now.isoformat(),
            },
            "money.get_recurring_payments": {
                "payments": [
                    {
                        "id": "rec_demo",
                        "merchant": "Netflix",
                        "amount": 15.49,
                        "currency": "USD",
                        "next_due": (now + timedelta(days=1)).date().isoformat(),
                    }
                ],
                "as_of": now.isoformat(),
            },
        }
        if name not in self.TOOLS:
            return CallToolResult(content=[TextContent(text="Tool is not available")], isError=True)
        payload = fixtures.get(
            name, {"items": [], "as_of": now.isoformat(), "arguments": arguments}
        )
        return CallToolResult(content=[], structuredContent=payload)
