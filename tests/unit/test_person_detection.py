"""Camera presence pipeline: frames are counted, then discarded."""

from __future__ import annotations

from typing import Any

from manny.vision import NullPersonDetector, Picamera2Adapter, build_person_detector


class _FakeCamera:
    def __init__(self, frames: list[object]) -> None:
        self.frames = frames
        self.started = False
        self.configured = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def create_preview_configuration(self, **kwargs: Any) -> Any:
        return kwargs

    def configure(self, configuration: Any) -> None:
        del configuration
        self.configured = True

    def capture_array(self) -> object:
        return self.frames.pop(0)


class _CountingDetector:
    def __init__(self, counts: list[int]) -> None:
        self.counts = counts
        self.seen: list[object] = []

    def count_people(self, frame: Any) -> int:
        self.seen.append(frame)
        return self.counts.pop(0)


def _attach(adapter: Picamera2Adapter, camera: _FakeCamera) -> None:
    adapter._camera = camera  # type: ignore[assignment]


async def test_frames_are_counted_by_the_configured_detector() -> None:
    detector = _CountingDetector([0, 2])
    adapter = Picamera2Adapter(detector)
    _attach(adapter, _FakeCamera(["frame-a", "frame-b"]))

    assert await adapter.people_count() == 0
    assert await adapter.people_count() == 2
    assert detector.seen == ["frame-a", "frame-b"]


async def test_detector_failure_degrades_to_no_presence() -> None:
    class BrokenDetector:
        def count_people(self, frame: Any) -> int:
            raise RuntimeError("detector crashed")

    adapter = Picamera2Adapter(BrokenDetector())
    _attach(adapter, _FakeCamera(["frame"]))

    assert await adapter.people_count() == 0


async def test_stopped_camera_reports_no_presence() -> None:
    adapter = Picamera2Adapter(_CountingDetector([3]))

    assert await adapter.people_count() == 0


async def test_external_detection_updates_are_accepted() -> None:
    adapter = Picamera2Adapter()

    adapter.update_local_detection(4)
    assert await adapter.people_count() == 4

    adapter.update_local_detection(-1)
    assert await adapter.people_count() == 0


def test_unknown_detector_backend_falls_back_to_null() -> None:
    assert isinstance(build_person_detector("none"), NullPersonDetector)
    assert isinstance(build_person_detector("nonsense"), NullPersonDetector)
    assert build_person_detector("opencv_hog").__class__.__name__ == "OpenCvHogPersonDetector"
