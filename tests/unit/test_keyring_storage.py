from mcp.shared.auth import OAuthToken

from manny.mcp.storage import KeyringTokenStorage


class FakeKeyring:
    value: str | None = None

    def get_password(self, service: str, username: str) -> str | None:
        del service, username
        return self.value

    def set_password(self, service: str, username: str, password: str) -> None:
        del service, username
        self.value = password

    def delete_password(self, service: str, username: str) -> None:
        del service, username
        self.value = None


async def test_keyring_storage_round_trip_and_reset() -> None:
    backend = FakeKeyring()
    storage = KeyringTokenStorage(backend, device_id="test-manny")

    await storage.set_tokens(OAuthToken(access_token="secret", token_type="Bearer"))
    restored = await storage.get_tokens()
    assert restored is not None
    assert restored.access_token == "secret"

    await storage.clear()
    assert await storage.get_tokens() is None
