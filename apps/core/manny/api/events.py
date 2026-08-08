"""Small in-process WebSocket event broadcaster."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class EventBus:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        message = {"type": event_type, "payload": payload}
        async with self._lock:
            clients = tuple(self._clients)
        stale: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(message)
            except RuntimeError:
                stale.append(client)
        if stale:
            async with self._lock:
                for client in stale:
                    self._clients.discard(client)
