"""Official-SDK Streamable HTTP client for the Money Copilot MCP server."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

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
from manny.mcp.storage import JsonTokenStorage

logger = logging.getLogger(__name__)
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
        self._storage = JsonTokenStorage(
            storage_path or REPOSITORY_ROOT / "data" / "mcp_oauth.json",
            initial_token=initial_token,
        )
        self._status = MCPStatus(
            phase=MCPConnectionPhase.CONNECTING,
            detail="Checking Money Copilot connection",
        )
        self._connection_lock = asyncio.Lock()
        self._authorization_ready = asyncio.Event()
        self._callback_future: asyncio.Future[AuthorizationCodeResult] | None = None
        self._authorization_task: asyncio.Task[None] | None = None

    @property
    def status(self) -> MCPStatus:
        return self._status

    def set_listener(self, listener: StatusListener) -> None:
        self._listener = listener

    async def start(self) -> None:
        await self._connect(interactive=False)

    async def stop(self) -> None:
        if self._authorization_task and not self._authorization_task.done():
            self._authorization_task.cancel()
            await asyncio.gather(self._authorization_task, return_exceptions=True)

    async def begin_authorization(self) -> MCPStatus:
        if self._status.connected:
            return self._status
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
        future = self._callback_future
        if future is None or future.done():
            await self._set_status(
                MCPConnectionPhase.ERROR,
                "No authorization request is waiting for this callback",
            )
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
        provider = self._oauth_provider(interactive=False)
        async with asyncio.timeout(self._settings.mcp_tool_timeout_seconds):
            async with httpx2.AsyncClient(auth=provider, follow_redirects=True) as http_client:
                transport = streamable_http_client(self._settings.mcp_url, http_client=http_client)
                async with Client(
                    transport,
                    mode="auto",
                    read_timeout_seconds=self._settings.mcp_tool_timeout_seconds,
                    client_info=Implementation(name="manny-os", version=__version__),
                ) as client:
                    return await client.call_tool(name, arguments)

    async def _connect(self, *, interactive: bool) -> None:
        async with self._connection_lock:
            await self._set_status(MCPConnectionPhase.CONNECTING, "Connecting to Money Copilot")
            provider = self._oauth_provider(interactive=interactive)
            try:
                async with asyncio.timeout(
                    None if interactive else self._settings.mcp_connect_timeout_seconds
                ):
                    async with httpx2.AsyncClient(
                        auth=provider,
                        follow_redirects=True,
                        timeout=self._settings.mcp_connect_timeout_seconds,
                    ) as http_client:
                        transport = streamable_http_client(
                            self._settings.mcp_url,
                            http_client=http_client,
                        )
                        async with Client(
                            transport,
                            mode="auto",
                            read_timeout_seconds=self._settings.mcp_connect_timeout_seconds,
                            client_info=Implementation(name="manny-os", version=__version__),
                        ) as client:
                            tools = await client.list_tools()
                            discovered = sorted(tool.name for tool in tools.tools)
                            server_name = (
                                client.server_info.name
                                if client.server_info
                                else "Money Copilot MCP"
                            )
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
