"""Raspberry Pi camera adapter loaded only on supported hardware."""

from __future__ import annotations

import importlib
from typing import Protocol, cast


class _Picamera(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...


class Picamera2Adapter:
    """Camera lifecycle boundary; detection is delegated to a local detector process."""

    def __init__(self) -> None:
        self._camera: _Picamera | None = None
        self._people_count = 0

    async def start(self) -> None:
        try:
            module = importlib.import_module("picamera2")
        except ImportError as exc:
            raise RuntimeError("Picamera2 is required on Raspberry Pi hardware") from exc
        camera_type = module.Picamera2
        self._camera = cast(_Picamera, camera_type())
        self._camera.start()

    async def stop(self) -> None:
        if self._camera is not None:
            self._camera.stop()
            self._camera = None

    async def people_count(self) -> int:
        return self._people_count

    def update_local_detection(self, count: int) -> None:
        self._people_count = max(0, count)
