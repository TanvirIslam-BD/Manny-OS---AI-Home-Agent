"""Durable conversational memory for Manny.

Only general conversation is retained. Financial answers are never written here:
balances, budgets, and category totals stay in the timestamped finance cache,
which expires and is cleared by a factory reset (ADR-004). Memory exists so
Manny can hold a thread across restarts, not so it can accumulate money facts.

The store is bounded. Once `limit` rows exist the oldest are dropped, so a device
running for months cannot fill its disk with chat history.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["user", "assistant"]


class MemoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    content: str = Field(min_length=1, max_length=1200)
    language: str = Field(default="en", min_length=2, max_length=35)
    created_at: datetime


class MemoryStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    entries: int = Field(ge=0)
    limit: int = Field(ge=0)
    oldest: datetime | None = None
    newest: datetime | None = None

    @property
    def full(self) -> bool:
        return self.limit > 0 and self.entries >= self.limit


class MemoryStore:
    def __init__(self, path: Path, *, limit: int = 400) -> None:
        self._path = path
        self._limit = limit
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._initialize_sync)

    async def remember(self, entries: list[MemoryEntry]) -> None:
        if not entries:
            return
        async with self._lock:
            await asyncio.to_thread(self._remember_sync, entries)

    async def recent(self, limit: int) -> list[MemoryEntry]:
        async with self._lock:
            rows = await asyncio.to_thread(self._recent_sync, limit)
        return [
            MemoryEntry(
                role=row[0],
                content=row[1],
                language=row[2],
                created_at=datetime.fromisoformat(row[3]),
            )
            for row in rows
        ]

    async def search(
        self, text: str, *, limit: int = 4, skip_newest: int = 0
    ) -> list[MemoryEntry]:
        """Find older entries relevant to the question being asked.

        A recent-window alone is not memory: anything said more turns ago than
        the window is held on disk but never consulted, so the model answers as
        though it were never told. This scores stored turns by term overlap and
        returns the best older matches so a fact stated long ago can still be
        recalled.
        """
        terms = _terms(text)
        if not terms or limit <= 0:
            return []
        async with self._lock:
            rows = await asyncio.to_thread(self._all_sync, skip_newest)
        scored: list[tuple[int, int, tuple[str, str, str, str]]] = []
        for row in rows:
            candidate = _terms(row[1])
            overlap = len(terms & candidate)
            if overlap:
                scored.append((overlap, row[4], (row[0], row[1], row[2], row[3])))
        # Best overlap first, then most recent; return in chronological order.
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        chosen = sorted(scored[:limit], key=lambda item: item[1])
        return [
            MemoryEntry(
                role=item[2][0],
                content=item[2][1],
                language=item[2][2],
                created_at=datetime.fromisoformat(item[2][3]),
            )
            for item in chosen
        ]

    async def stats(self) -> MemoryStats:
        async with self._lock:
            entries, oldest, newest = await asyncio.to_thread(self._stats_sync)
        return MemoryStats(
            entries=entries,
            limit=self._limit,
            oldest=datetime.fromisoformat(oldest) if oldest else None,
            newest=datetime.fromisoformat(newest) if newest else None,
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
                """CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL,
                content TEXT NOT NULL, language TEXT NOT NULL, created_at TEXT NOT NULL)"""
            )

    def _remember_sync(self, entries: list[MemoryEntry]) -> None:
        with self._connect() as connection:
            connection.executemany(
                "INSERT INTO memory (role, content, language, created_at) VALUES (?, ?, ?, ?)",
                [
                    (item.role, item.content, item.language, item.created_at.isoformat())
                    for item in entries
                ],
            )
            # Bounded: drop the oldest rows once the ceiling is passed.
            connection.execute(
                "DELETE FROM memory WHERE id NOT IN "
                "(SELECT id FROM memory ORDER BY id DESC LIMIT ?)",
                (self._limit,),
            )

    def _recent_sync(self, limit: int) -> list[tuple[str, str, str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT role, content, language, created_at FROM memory "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [(row[0], row[1], row[2], row[3]) for row in reversed(rows)]

    def _all_sync(self, skip_newest: int) -> list[tuple[str, str, str, str, int]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT role, content, language, created_at, id FROM memory "
                "ORDER BY id DESC LIMIT -1 OFFSET ?",
                (max(0, skip_newest),),
            ).fetchall()
        return [(row[0], row[1], row[2], row[3], int(row[4])) for row in rows]

    def _stats_sync(self) -> tuple[int, str | None, str | None]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM memory"
            ).fetchone()
        return (int(row[0]), row[1], row[2])

    def _clear_sync(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM memory")


# Common grammar must not match every stored turn.
_STOPWORDS = frozenset({
    "an", "and", "are", "as", "at", "be", "by", "can", "could", "do", "does", "for", "from",
    "had", "has", "have", "he", "her", "him", "his", "how", "i", "if", "in", "into", "is",
    "it", "its", "me", "my", "of", "on", "or", "our", "she", "that", "the",
    "their", "them", "then", "there", "they", "this", "to", "was", "we", "were", "what",
    "when", "where", "which", "who", "will", "with", "would", "you", "your",
})
_WORD = re.compile(r"\w+", re.UNICODE)


def _terms(text: str) -> set[str]:
    """Content words only, so common grammar does not match everything."""
    return {
        word
        for word in (match.group().casefold() for match in _WORD.finditer(text))
        if word not in _STOPWORDS and len(word) > 1
    }


def entries_from_turn(question: str, answer: str, language: str) -> list[MemoryEntry]:
    now = datetime.now(UTC)
    return [
        MemoryEntry(role="user", content=question[:1200], language=language, created_at=now),
        MemoryEntry(role="assistant", content=answer[:1200], language=language, created_at=now),
    ]
