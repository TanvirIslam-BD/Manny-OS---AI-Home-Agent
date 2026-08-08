"""Minimal timestamped cache for offline finance display and responses."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class CachedFinanceResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    payload: dict[str, object]
    source: str
    fetched_at: datetime
    expires_at: datetime


class FinanceCache:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._initialize_sync)

    async def put(
        self,
        key: str,
        payload: dict[str, object],
        *,
        source: str,
        ttl: timedelta = timedelta(minutes=15),
    ) -> CachedFinanceResult:
        now = datetime.now(UTC)
        item = CachedFinanceResult(
            key=key,
            payload=payload,
            source=source,
            fetched_at=now,
            expires_at=now + ttl,
        )
        async with self._lock:
            await asyncio.to_thread(self._put_sync, item)
        return item

    async def get(self, key: str) -> CachedFinanceResult | None:
        async with self._lock:
            row = await asyncio.to_thread(self._get_sync, key)
        if row is None:
            return None
        return CachedFinanceResult(
            key=row[0],
            payload=json.loads(row[1]),
            source=row[2],
            fetched_at=datetime.fromisoformat(row[3]),
            expires_at=datetime.fromisoformat(row[4]),
        )

    async def clear(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._clear_sync)

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self._path)

    def _initialize_sync(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS finance_cache (
                key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, source TEXT NOT NULL,
                fetched_at TEXT NOT NULL, expires_at TEXT NOT NULL)"""
            )

    def _put_sync(self, item: CachedFinanceResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO finance_cache
                (key, payload_json, source, fetched_at, expires_at) VALUES (?, ?, ?, ?, ?)""",
                (
                    item.key,
                    json.dumps(item.payload, separators=(",", ":")),
                    item.source,
                    item.fetched_at.isoformat(),
                    item.expires_at.isoformat(),
                ),
            )

    def _get_sync(self, key: str) -> tuple[str, str, str, str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT key, payload_json, source, fetched_at, expires_at "
                "FROM finance_cache WHERE key = ?",
                (key,),
            ).fetchone()
        return row if row is None else (row[0], row[1], row[2], row[3], row[4])

    def _clear_sync(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM finance_cache")
