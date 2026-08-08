"""Development OAuth token storage kept outside Git and model context."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Protocol

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


class JsonTokenStorage:
    """Persist OAuth material in a restrictive local file for development.

    Production devices must replace this with the secure provisioning adapter described in
    the requirements. Values from this class must never be logged or exposed through the API.
    """

    def __init__(self, path: Path, initial_token: OAuthToken | None = None) -> None:
        self._path = path
        self._initial_token = initial_token
        self._lock = asyncio.Lock()

    async def get_tokens(self) -> OAuthToken | None:
        async with self._lock:
            data = self._read()
            raw = data.get("tokens")
            if isinstance(raw, dict):
                try:
                    return OAuthToken.model_validate(raw)
                except ValueError:
                    return None
            return self._initial_token

    async def set_tokens(self, tokens: OAuthToken) -> None:
        async with self._lock:
            data = self._read()
            data["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
            self._write(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        async with self._lock:
            raw = self._read().get("client_info")
            if not isinstance(raw, dict):
                return None
            try:
                return OAuthClientInformationFull.model_validate(raw)
            except ValueError:
                return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        async with self._lock:
            data = self._read()
            data["client_info"] = client_info.model_dump(mode="json", exclude_none=True)
            self._write(data)

    async def clear(self) -> None:
        async with self._lock:
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                return

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self._path)
        os.chmod(self._path, 0o600)


class KeyringBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class KeyringTokenStorage:
    """OAuth storage backed by the operating system credential vault."""

    def __init__(
        self,
        backend: KeyringBackend,
        *,
        device_id: str,
        service: str = "manny-os-money-copilot",
    ) -> None:
        self._backend = backend
        self._service = service
        self._username = device_id
        self._lock = asyncio.Lock()

    async def get_tokens(self) -> OAuthToken | None:
        raw = (await self._read()).get("tokens")
        return OAuthToken.model_validate(raw) if isinstance(raw, dict) else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        async with self._lock:
            data = self._read_sync()
            data["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
            self._write_sync(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = (await self._read()).get("client_info")
        return OAuthClientInformationFull.model_validate(raw) if isinstance(raw, dict) else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        async with self._lock:
            data = self._read_sync()
            data["client_info"] = client_info.model_dump(mode="json", exclude_none=True)
            self._write_sync(data)

    async def clear(self) -> None:
        async with self._lock:
            try:
                self._backend.delete_password(self._service, self._username)
            except Exception:
                return

    async def _read(self) -> dict[str, Any]:
        async with self._lock:
            return self._read_sync()

    def _read_sync(self) -> dict[str, Any]:
        raw = self._backend.get_password(self._service, self._username)
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def _write_sync(self, data: dict[str, Any]) -> None:
        self._backend.set_password(
            self._service,
            self._username,
            json.dumps(data, separators=(",", ":")),
        )
