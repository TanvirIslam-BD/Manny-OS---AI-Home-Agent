"""Local person detection behind a replaceable boundary.

Frames are counted and discarded in place; nothing here retains or writes image
data (ADR-005). Accelerator-backed detectors (IMX500, Hailo) can be added as
further implementations of `PersonDetector` without touching the camera adapter.
"""

from __future__ import annotations

import importlib
from typing import Any, Protocol


class PersonDetector(Protocol):
    def count_people(self, frame: Any) -> int: ...


class NullPersonDetector:
    """Default when no detector is configured: presence is reported as unknown-empty."""

    @property
    def available(self) -> bool:
        return False

    def count_people(self, frame: Any) -> int:
        del frame
        return 0


class OpenCvHogPersonDetector:
    """CPU HOG + linear SVM pedestrian detector, imported only when configured."""

    def __init__(self, *, stride: int = 8, padding: int = 8, scale: float = 1.05) -> None:
        self._stride = stride
        self._padding = padding
        self._scale = scale
        self._descriptor: Any = None

    @property
    def available(self) -> bool:
        return True

    def count_people(self, frame: Any) -> int:
        cv2 = importlib.import_module("cv2")
        if self._descriptor is None:
            descriptor = cv2.HOGDescriptor()
            descriptor.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            self._descriptor = descriptor
        rectangles, _weights = self._descriptor.detectMultiScale(
            frame,
            winStride=(self._stride, self._stride),
            padding=(self._padding, self._padding),
            scale=self._scale,
        )
        return int(len(rectangles))


def build_person_detector(backend: str) -> PersonDetector:
    if backend == "opencv_hog":
        return OpenCvHogPersonDetector()
    return NullPersonDetector()
