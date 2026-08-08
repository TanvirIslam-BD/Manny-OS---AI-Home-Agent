"""Raspberry Pi camera adapter loaded only on supported hardware."""

from __future__ import annotations

import asyncio
import importlib
import io
import logging
from typing import Any, Protocol, cast

from manny.vision.detector import NullPersonDetector, PersonDetector

logger = logging.getLogger(__name__)


class _Picamera(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def capture_array(self) -> Any: ...
    def capture_file(self, target: Any, format: str = ...) -> Any: ...
    def create_preview_configuration(self, **kwargs: Any) -> Any: ...
    def configure(self, configuration: Any) -> None: ...


class Picamera2Adapter:
    """Captures presence-only frames and discards them immediately after counting."""

    def __init__(
        self,
        detector: PersonDetector | None = None,
        *,
        resolution: tuple[int, int] = (640, 480),
    ) -> None:
        self._camera: _Picamera | None = None
        self._detector = detector or NullPersonDetector()
        self._resolution = resolution
        self._people_count = 0

    async def start(self) -> None:
        try:
            module = importlib.import_module("picamera2")
        except ImportError as exc:
            raise RuntimeError("Picamera2 is required on Raspberry Pi hardware") from exc
        camera_type = module.Picamera2
        camera = cast(_Picamera, camera_type())
        camera.configure(camera.create_preview_configuration(main={"size": self._resolution}))
        camera.start()
        self._camera = camera

    async def stop(self) -> None:
        if self._camera is not None:
            self._camera.stop()
            self._camera = None
        self._people_count = 0

    async def people_count(self) -> int:
        if self._camera is None:
            return self._people_count
        return await asyncio.to_thread(self._count_sync)

    def _count_sync(self) -> int:
        camera = self._camera
        if camera is None:
            return self._people_count
        try:
            # The frame stays a local reference and is released on return; it is
            # never written to disk or forwarded off-device.
            frame = camera.capture_array()
            self._people_count = max(0, self._detector.count_people(frame))
        except Exception:
            # A detector or capture failure must degrade to "nobody detected"
            # rather than kill the polling task that owns this call.
            logger.warning("presence detection failed; reporting no presence")
            self._people_count = 0
        return self._people_count

    async def capture_frame(self) -> bytes | None:
        """A JPEG for the vision model, encoded in memory and never written out."""
        if self._camera is None:
            return None
        return await asyncio.to_thread(self._capture_frame_sync)

    def _capture_frame_sync(self) -> bytes | None:
        camera = self._camera
        if camera is None:
            return None
        try:
            buffer = io.BytesIO()
            camera.capture_file(buffer, format="jpeg")
            return buffer.getvalue() or None
        except Exception:
            logger.warning("camera frame capture failed")
            return None

    def update_local_detection(self, count: int) -> None:
        """Accept a count from an external detector process."""
        self._people_count = max(0, count)
