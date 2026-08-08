import pytest

from manny.hardware.mock import MockCamera, MockDisplay


@pytest.mark.asyncio
async def test_mock_camera_discards_presence_when_stopped() -> None:
    camera = MockCamera(simulated_people_count=1)
    await camera.start()
    assert await camera.people_count() == 1

    await camera.stop()
    assert await camera.people_count() == 0


@pytest.mark.asyncio
async def test_mock_display_clamps_brightness() -> None:
    display = MockDisplay()
    await display.set_brightness(4)
    assert display.brightness == 1
