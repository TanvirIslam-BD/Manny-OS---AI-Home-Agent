from manny.hardware.mock import MockCamera
from manny.state import PrivacyState, RuntimeState, StateMachine
from manny.vision import PresenceEvent, VisionService


async def test_presence_service_wakes_ui_without_persisting_frames() -> None:
    camera = MockCamera(simulated_people_count=1)
    await camera.start()
    state = StateMachine()
    events: list[PresenceEvent] = []

    async def receive(event: PresenceEvent) -> None:
        events.append(event)

    vision = VisionService(camera, state, receive)
    event = await vision.poll_once()

    assert event is not None
    assert event.model_dump().keys() == {
        "type",
        "present",
        "people_count",
        "confidence",
        "timestamp",
    }
    assert state.snapshot.state is RuntimeState.PRESENT
    assert state.snapshot.privacy is PrivacyState.PRESENT_UNKNOWN


async def test_multiple_people_activate_private_mode() -> None:
    camera = MockCamera(simulated_people_count=2)
    await camera.start()
    state = StateMachine()

    async def ignore(_event: PresenceEvent) -> None:
        return None

    await VisionService(camera, state, ignore).poll_once()
    assert state.snapshot.privacy is PrivacyState.MULTIPLE_PEOPLE
