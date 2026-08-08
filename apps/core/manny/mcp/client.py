"""Official-SDK Streamable HTTP client for the Money Copilot MCP server."""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from time import monotonic

import httpx2
from mcp import Client
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientMetadata, OAuthToken
from mcp_types import CallToolResult, Implementation
from pydantic import AnyUrl

from manny import __version__
from manny.config import REPOSITORY_ROOT, Settings
from manny.mcp.models import MCPConnectionPhase, MCPStatus
from manny.mcp.storage import JsonTokenStorage, KeyringTokenStorage

logger = logging.getLogger(__name__)
_RECONNECT_BACKOFF_SECONDS = 30.0
StatusListener = Callable[[MCPStatus], Awaitable[None]]


class AuthorizationRequiredError(RuntimeError):
    pass


class ToolNotAllowedError(PermissionError):
    pass


class AuthorizationRejectedError(RuntimeError):
    pass


class MoneyCopilotMCPClient:
    """Discovers and calls approved tools without exposing tokens to the UI or agent."""

    def __init__(
        self,
        settings: Settings,
        listener: StatusListener | None = None,
        storage_path: Path | None = None,
    ) -> None:
        self._settings = settings
        self._listener = listener
        initial_token = None
        if settings.mcp_access_token and settings.mcp_access_token.get_secret_value():
            initial_token = OAuthToken(
                access_token=settings.mcp_access_token.get_secret_value(),
                scope="mcp:tools mcp:resources mcp:prompts",
            )
        self._storage: JsonTokenStorage | KeyringTokenStorage
        if settings.mcp_token_storage == "keyring":
            try:
                keyring = importlib.import_module("keyring")
            except ImportError as exc:
                raise RuntimeError("install Manny's production keyring dependency") from exc
            methods = ("get_password", "set_password", "delete_password")
            if not all(hasattr(keyring, name) for name in methods):
                raise RuntimeError("installed keyring backend is incompatible")
            self._storage = KeyringTokenStorage(
                keyring,
                device_id=settings.device_id,
            )
        else:
            self._storage = JsonTokenStorage(
                storage_path or REPOSITORY_ROOT / "data" / "mcp_oauth.json",
                initial_token=initial_token,
            )
        self._status = MCPStatus(
            phase=MCPConnectionPhase.CONNECTING,
            detail="Checking Money Copilot connection",
        )
        self._connection_lock = asyncio.Lock()
        self._tool_lock = asyncio.Lock()
        self._session_client: Client | None = None
        self._session_stack: AsyncExitStack | None = None
        self._authorization_ready = asyncio.Event()
        self._callback_future: asyncio.Future[AuthorizationCodeResult] | None = None
        self._authorization_task: asyncio.Task[None] | None = None
        self._startup_task: asyncio.Task[None] | None = None
        self._reconnect_after = 0.0

    @property
    def status(self) -> MCPStatus:
        return self._status

    def set_listener(self, listener: StatusListener) -> None:
        self._listener = listener

    async def start(self) -> None:
        if self._startup_task is None or self._startup_task.done():
            self._startup_task = asyncio.create_task(self._connect(interactive=False))
            await asyncio.sleep(0)

    async def stop(self) -> None:
        await self._cancel_task(self._authorization_task)
        await self._cancel_task(self._startup_task)
        await self._close_session()

    async def reset_credentials(self) -> None:
        await self.stop()
        await self._storage.clear()
        await self._set_status(
            MCPConnectionPhase.AUTH_REQUIRED,
            "Money Copilot account authorization is required",
        )

    async def begin_authorization(self) -> MCPStatus:
        if self._status.connected:
            return self._status
        await self._cancel_task(self._startup_task)
        if self._authorization_task and not self._authorization_task.done():
            return self._status

        self._authorization_ready.clear()
        self._callback_future = asyncio.get_running_loop().create_future()
        self._authorization_task = asyncio.create_task(self._connect(interactive=True))
        try:
            async with asyncio.timeout(self._settings.mcp_connect_timeout_seconds):
                await self._authorization_ready.wait()
        except TimeoutError:
            await self._set_status(
                MCPConnectionPhase.ERROR,
                "Authorization did not start in time",
            )
        return self._status

    async def complete_authorization(self, result: AuthorizationCodeResult) -> MCPStatus:
        if self._status.connected:
            return self._status

        future = self._callback_future
        if future is None or future.done():
            task = self._authorization_task
            if task is not None and not task.done():
                try:
                    async with asyncio.timeout(self._settings.mcp_connect_timeout_seconds):
                        await asyncio.shield(task)
                except TimeoutError:
                    pass
            if self._status.connected:
                return self._status
            await self._connect(interactive=False)
            return self._status

        self._authorization_ready.clear()
        future.set_result(result)
        if self._authorization_task:
            try:
                async with asyncio.timeout(self._settings.mcp_connect_timeout_seconds):
                    await asyncio.shield(self._authorization_task)
            except TimeoutError:
                await self._set_status(
                    MCPConnectionPhase.ERROR,
                    "Authorization callback timed out",
                )
        return self._status

    async def fail_authorization(self, detail: str) -> MCPStatus:
        future = self._callback_future
        if future is not None and not future.done():
            future.set_exception(AuthorizationRejectedError(detail))
        await self._set_status(MCPConnectionPhase.ERROR, detail)
        return self._status

    async def call_tool(self, name: str, arguments: dict[str, object]) -> CallToolResult:
        if name not in self._settings.allowed_mcp_tools:
            raise ToolNotAllowedError(f"MCP tool is not allowlisted: {name}")
        if self._session_client is None:
            # Reconnecting inline on every call made each question wait out the full
            # connect timeout before falling back to cache. Fail fast instead when a
            # retry cannot help, and rate-limit the ones that might.
            if self._status.phase is MCPConnectionPhase.AUTH_REQUIRED:
                raise AuthorizationRequiredError("Money Copilot authorization is required")
            if monotonic() < self._reconnect_after:
                raise RuntimeError("Money Copilot session is unavailable")
            self._reconnect_after = monotonic() + _RECONNECT_BACKOFF_SECONDS
            await self._connect(interactive=False)
        client = self._session_client
        if client is None:
            raise RuntimeError("Money Copilot session is unavailable")
        async with self._tool_lock:
            async with asyncio.timeout(self._settings.mcp_tool_timeout_seconds):
                return await client.call_tool(name, arguments)

    async def _connect(self, *, interactive: bool) -> None:
        async with self._connection_lock:
            await self._close_session()
            await self._set_status(MCPConnectionPhase.CONNECTING, "Connecting to Money Copilot")
            provider = self._oauth_provider(interactive=interactive)
            active_stack = AsyncExitStack()
            stack: AsyncExitStack | None = active_stack
            await active_stack.__aenter__()
            try:
                async with asyncio.timeout(
                    None if interactive else self._settings.mcp_connect_timeout_seconds
                ):
                    http_client = await active_stack.enter_async_context(
                        httpx2.AsyncClient(
                            auth=provider,
                            follow_redirects=True,
                            timeout=self._settings.mcp_connect_timeout_seconds,
                        )
                    )
                    transport = streamable_http_client(
                        self._settings.mcp_url,
                        http_client=http_client,
                    )
                    client = await active_stack.enter_async_context(
                        Client(
                            transport,
                            mode="auto",
                            read_timeout_seconds=self._settings.mcp_connect_timeout_seconds,
                            client_info=Implementation(name="manny-os", version=__version__),
                        )
                    )
                    tools = await client.list_tools()
                    discovered = sorted(tool.name for tool in tools.tools)
                    server_name = (
                        client.server_info.name if client.server_info else "Money Copilot MCP"
                    )
                    self._session_client = client
                    self._session_stack = active_stack
                    stack = None
                    self._reconnect_after = 0.0
                    await self._set_status(
                        MCPConnectionPhase.CONNECTED,
                        f"Connected with {len(discovered)} tools discovered",
                        server_name=server_name,
                        protocol_version=client.protocol_version,
                        discovered_tools=discovered,
                    )
            except TimeoutError:
                await self._set_status(
                    MCPConnectionPhase.DEGRADED,
                    "Money Copilot connection timed out",
                )
            except Exception as exc:  # SDK/network boundary; never log credential-bearing details
                if _contains_exception(exc, AuthorizationRequiredError):
                    if self._status.phase != MCPConnectionPhase.AUTH_REQUIRED:
                        await self._set_status(
                            MCPConnectionPhase.AUTH_REQUIRED,
                            "Money Copilot account authorization is required",
                        )
                elif _contains_status(exc, {401, 403}):
                    await self._set_status(
                        MCPConnectionPhase.AUTH_REQUIRED,
                        "Money Copilot account authorization is required",
                    )
                elif _contains_exception(exc, AuthorizationRejectedError):
                    await self._set_status(
                        MCPConnectionPhase.ERROR,
                        "Money Copilot authorization was cancelled",
                    )
                else:
                    logger.warning("Money Copilot MCP connection failed: %s", type(exc).__name__)
                    await self._set_status(
                        MCPConnectionPhase.DEGRADED,
                        "Money Copilot is unavailable or authorization was rejected",
                    )
            finally:
                if stack is not None:
                    await stack.aclose()

    async def _close_session(self) -> None:
        stack, self._session_stack = self._session_stack, None
        self._session_client = None
        if stack is not None:
            await stack.aclose()

    def _oauth_provider(self, *, interactive: bool) -> OAuthClientProvider:
        redirect_uri = AnyUrl(
            f"http://{self._settings.api_host}:{self._settings.api_port}/api/mcp/oauth/callback"
        )
        metadata = OAuthClientMetadata(
            client_name="Manny Copilot",
            software_id="manny-os",
            software_version=__version__,
            redirect_uris=[redirect_uri],
            token_endpoint_auth_method="none",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope="mcp:tools mcp:resources mcp:prompts",
        )
        callback = self._wait_for_callback if interactive else self._reject_callback
        return OAuthClientProvider(
            server_url=self._settings.mcp_url,
            client_metadata=metadata,
            storage=self._storage,
            redirect_handler=self._handle_redirect,
            callback_handler=callback,
        )

    async def _handle_redirect(self, authorization_url: str) -> None:
        authorization_url = _normalize_authorization_url(authorization_url)
        await self._set_status(
            MCPConnectionPhase.AUTH_REQUIRED,
            "Approve Manny in Money Copilot to continue",
            authorization_url=authorization_url,
        )
        self._authorization_ready.set()

    async def _wait_for_callback(self) -> AuthorizationCodeResult:
        if self._callback_future is None:
            self._callback_future = asyncio.get_running_loop().create_future()
        return await self._callback_future

    async def _reject_callback(self) -> AuthorizationCodeResult:
        raise AuthorizationRequiredError("interactive authorization required")

    async def _set_status(
        self,
        phase: MCPConnectionPhase,
        detail: str,
        *,
        server_name: str | None = None,
        protocol_version: str | None = None,
        authorization_url: str | None = None,
        discovered_tools: list[str] | None = None,
    ) -> None:
        self._status = MCPStatus(
            phase=phase,
            connected=phase == MCPConnectionPhase.CONNECTED,
            server_name=server_name or self._status.server_name,
            protocol_version=protocol_version or self._status.protocol_version,
            authorization_url=(
                authorization_url
                if authorization_url is not None or phase == MCPConnectionPhase.CONNECTED
                else self._status.authorization_url
            ),
            discovered_tools=discovered_tools or self._status.discovered_tools,
            allowed_tools=sorted(self._settings.allowed_mcp_tools),
            detail=detail,
        )
        if phase in {
            MCPConnectionPhase.CONNECTED,
            MCPConnectionPhase.ERROR,
            MCPConnectionPhase.DEGRADED,
        }:
            self._authorization_ready.set()
        if self._listener:
            await self._listener(self._status)

    @staticmethod
    async def _cancel_task(task: asyncio.Task[None] | None) -> None:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def _contains_status(exception: BaseException, codes: set[int]) -> bool:
    """Detect a rejected credential anywhere in a wrapped transport failure."""
    response = getattr(exception, "response", None)
    if response is not None and getattr(response, "status_code", None) in codes:
        return True
    if isinstance(exception, BaseExceptionGroup):
        return any(_contains_status(item, codes) for item in exception.exceptions)
    return False


def _contains_exception(exception: BaseException, expected: type[BaseException]) -> bool:
    if isinstance(exception, expected):
        return True
    if isinstance(exception, BaseExceptionGroup):
        return any(_contains_exception(item, expected) for item in exception.exceptions)
    return False


def _normalize_authorization_url(url: str) -> str:
    """Preserve query parameters when an authorization endpoint already has a query."""

    base, separator, query = url.partition("?")
    if not separator or "?" not in query:
        return url
    endpoint_query, oauth_query = query.split("?", 1)
    return f"{base}?{endpoint_query}&{oauth_query}"
