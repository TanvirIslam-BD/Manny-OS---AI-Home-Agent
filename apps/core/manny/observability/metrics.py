from __future__ import annotations

import asyncio
from collections import Counter


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()
        self._lock = asyncio.Lock()

    async def increment(self, name: str, value: int = 1) -> None:
        async with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict[str, int]:
        return dict(self._counters)
