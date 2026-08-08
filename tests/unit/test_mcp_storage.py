from pathlib import Path

import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from manny.mcp.storage import JsonTokenStorage


@pytest.mark.asyncio
async def test_oauth_storage_round_trip(tmp_path: Path) -> None:
    storage = JsonTokenStorage(tmp_path / "mcp.json")
    tokens = OAuthToken(access_token="test-token", refresh_token="refresh-token")
    client = OAuthClientInformationFull(client_id="manny-test")

    await storage.set_tokens(tokens)
    await storage.set_client_info(client)

    assert await storage.get_tokens() == tokens
    assert await storage.get_client_info() == client
    assert "test-token" in (tmp_path / "mcp.json").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_invalid_oauth_storage_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text("not-json", encoding="utf-8")
    storage = JsonTokenStorage(path)

    assert await storage.get_tokens() is None
