import pytest
from mcp.shared.auth import OAuthToken

from manny.mcp.storage import (
    KeyringTokenStorage,
    KeyringUnavailableError,
    verify_keyring_backend,
)


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


class NoVaultKeyring:
    """A module-shaped object with no vault behind it.

    This is what the real keyring package looks like on a host with no Secret
    Service: the API is present, so an hasattr check passes, and the failure only
    appears when something tries to use it.
    """

    def get_password(self, service: str, username: str) -> str | None:
        del service, username
        raise RuntimeError("No recommended backend was available")

    def set_password(self, service: str, username: str, password: str) -> None:
        del service, username, password
        raise RuntimeError("No recommended backend was available")

    def delete_password(self, service: str, username: str) -> None:
        del service, username
        raise RuntimeError("No recommended backend was available")


def test_verify_keyring_backend_accepts_a_working_vault() -> None:
    verify_keyring_backend(FakeKeyring(), device_id="test-manny")


def test_verify_keyring_backend_rejects_a_vaultless_host() -> None:
    # Must fail here rather than midway through authorization, which is what the
    # previous hasattr check allowed.
    with pytest.raises(KeyringUnavailableError, match="no usable OS credential vault"):
        verify_keyring_backend(NoVaultKeyring(), device_id="test-manny")


def test_verify_keyring_backend_rejects_an_incompatible_module() -> None:
    class NotAKeyring:
        pass

    with pytest.raises(KeyringUnavailableError):
        verify_keyring_backend(NotAKeyring(), device_id="test-manny")  # type: ignore[arg-type]
