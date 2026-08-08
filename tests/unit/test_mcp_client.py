from pathlib import Path

import pytest

from manny.config import Settings
from manny.mcp.client import (
    MoneyCopilotMCPClient,
    ToolNotAllowedError,
    _normalize_authorization_url,
)


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
