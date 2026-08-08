from pathlib import Path
from time import monotonic

import pytest
from mcp.shared.auth import AuthorizationCodeResult

from manny.config import Settings
from manny.mcp.client import (
    MoneyCopilotMCPClient,
    ToolNotAllowedError,
    _normalize_authorization_url,
)
from manny.mcp.models import MCPConnectionPhase, MCPStatus


@pytest.mark.asyncio
async def test_non_allowlisted_tool_is_blocked_before_network(tmp_path: Path) -> None:
    settings = Settings(
        mcp_mode="remote_http",
        mcp_url="https://example.test/mcp",
        mcp_allowed_tools="money.get_budget_summary",
        _env_file=None,
    )
    client = MoneyCopilotMCPClient(settings, storage_path=tmp_path / "oauth.json")

    with pytest.raises(ToolNotAllowedError):
        await client.call_tool("money.add_manual_expense", {})


def test_authorization_endpoint_query_is_preserved() -> None:
    url = "https://auth.example/authorize?server_id=123?response_type=code&state=abc"

    assert _normalize_authorization_url(url) == (
        "https://auth.example/authorize?server_id=123&response_type=code&state=abc"
    )


@pytest.mark.asyncio
async def test_duplicate_oauth_callback_preserves_connected_state(tmp_path: Path) -> None:
    settings = Settings(
        mcp_mode="remote_http",
        mcp_url="https://example.test/mcp",
        _env_file=None,
    )
    client = MoneyCopilotMCPClient(settings, storage_path=tmp_path / "oauth.json")
    client._status = MCPStatus(
        phase=MCPConnectionPhase.CONNECTED,
        connected=True,
        protocol_version="2025-11-25",
        detail="Connected",
    )

    status = await client.complete_authorization(
        AuthorizationCodeResult(code="duplicate", state="duplicate")
    )

    assert status.connected is True
    assert status.phase is MCPConnectionPhase.CONNECTED


@pytest.mark.asyncio
async def test_unreachable_server_fails_fast_instead_of_retrying_every_call() -> None:
    """A blocked session must not make each question wait out the connect timeout."""
    from time import perf_counter

    from manny.mcp.client import AuthorizationRequiredError, MoneyCopilotMCPClient
    from manny.mcp.models import MCPConnectionPhase

    settings = Settings(
        mcp_mode="remote_http",
        mcp_url="https://example.invalid/mcp",
        mcp_allowed_tools="get_budget_status",
        _env_file=None,
    )
    client = MoneyCopilotMCPClient(settings)

    # Authorization is a state a retry cannot fix; it must raise immediately.
    await client._set_status(MCPConnectionPhase.AUTH_REQUIRED, "authorize")
    started = perf_counter()
    with pytest.raises(AuthorizationRequiredError):
        await client.call_tool("get_budget_status", {})
    assert perf_counter() - started < 1.0

    # A degraded session retries once, then backs off rather than reconnecting
    # on every subsequent call.
    await client._set_status(MCPConnectionPhase.DEGRADED, "unavailable")
    client._reconnect_after = monotonic() + 30
    started = perf_counter()
    with pytest.raises(RuntimeError):
        await client.call_tool("get_budget_status", {})
    assert perf_counter() - started < 1.0
