from __future__ import annotations

import asyncio
import builtins
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from manny.reminders.models import Reminder, ReminderCreate


class ReminderStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._initialize_sync)

    async def create(self, request: ReminderCreate) -> Reminder:
        reminder = Reminder(
            id=str(uuid.uuid4()),
            title=request.title,
            due_at=request.due_at,
            created_at=datetime.now(UTC),
        )
        async with self._lock:
            await asyncio.to_thread(self._create_sync, reminder)
        return reminder

    async def list(self, *, include_completed: bool = False) -> list[Reminder]:
        async with self._lock:
            rows = await asyncio.to_thread(self._list_sync, include_completed)
        return [self._from_row(row) for row in rows]

    async def complete(self, reminder_id: str) -> bool:
        async with self._lock:
            return await asyncio.to_thread(self._complete_sync, reminder_id)

    async def clear(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._clear_sync)

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self._path)

    def _initialize_sync(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, due_at TEXT NOT NULL,
                created_at TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0)"""
            )

    def _create_sync(self, reminder: Reminder) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO reminders (id, title, due_at, created_at, completed) "
                "VALUES (?, ?, ?, ?, 0)",
                (
                    reminder.id,
                    reminder.title,
                    reminder.due_at.isoformat(),
                    reminder.created_at.isoformat(),
                ),
            )

    def _list_sync(self, include_completed: bool) -> builtins.list[tuple[str, str, str, str, int]]:
        query = "SELECT id, title, due_at, created_at, completed FROM reminders"
        if not include_completed:
            query += " WHERE completed = 0"
        query += " ORDER BY due_at"
        with self._connect() as connection:
            return list(connection.execute(query).fetchall())

    def _complete_sync(self, reminder_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE reminders SET completed = 1 WHERE id = ?", (reminder_id,)
            )
        return cursor.rowcount == 1

    def _clear_sync(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM reminders")

    @staticmethod
    def _from_row(row: tuple[str, str, str, str, int]) -> Reminder:
        return Reminder(
            id=row[0],
            title=row[1],
            due_at=datetime.fromisoformat(row[2]),
            created_at=datetime.fromisoformat(row[3]),
            completed=bool(row[4]),
        )
