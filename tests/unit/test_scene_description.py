"""Answering about what the camera sees, and refusing to when others are present."""

from __future__ import annotations

from pathlib import Path

from manny.agent import RuleBasedAgent, ToolBroker
from manny.agent.models import AgentQuery
from manny.agent.runtime import DeterministicIntentModel
from manny.hardware.mock import MockCamera
from manny.mcp import MockMCPClient
from manny.policy import PolicyEngine
from manny.state import PrivacyState
from manny.vision import SceneAnswer, UnavailableVisionModel


class StubVision:
    def __init__(self) -> None:
        self.frames: list[bytes] = []

    @property
    def status(self) -> str:
        return "ok"

    async def describe(self, frame: bytes, question: str, language: str) -> SceneAnswer:
        self.frames.append(frame)
        return SceneAnswer(answer=f"I can see a desk. ({question})", language=language)


async def build(camera: MockCamera, vision: object | None) -> RuleBasedAgent:
    return RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()),
        remote=False,
        camera=camera,
        vision_model=vision,  # type: ignore[arg-type]
    )


async def test_scene_questions_are_recognised() -> None:
    model = DeterministicIntentModel()

    for text in ["what do you see", "what am I holding", "read this label", "look at this"]:
        assert await model.classify(text) == "describe_scene", text


async def test_a_frame_is_captured_and_described() -> None:
    camera = MockCamera()
    await camera.start()
    vision = StubVision()
    agent = await build(camera, vision)

    response = await agent.answer(
        AgentQuery(text="what do you see"), privacy=PrivacyState.PRIVATE_IDLE
    )

    assert response.intent == "describe_scene"
    assert "desk" in response.answer
    assert vision.frames, "the camera frame never reached the model"


async def test_the_view_is_not_described_while_others_are_present() -> None:
    camera = MockCamera()
    await camera.start()
    vision = StubVision()
    agent = await build(camera, vision)

    response = await agent.answer(
        AgentQuery(text="what do you see"), privacy=PrivacyState.MULTIPLE_PEOPLE
    )

    assert response.requires_authentication is True
    assert vision.frames == [], "a frame was sent despite the privacy state"


async def test_without_a_model_manny_says_so_rather_than_inventing() -> None:
    camera = MockCamera()
    await camera.start()
    agent = await build(camera, UnavailableVisionModel())

    response = await agent.answer(
        AgentQuery(text="what do you see"), privacy=PrivacyState.PRIVATE_IDLE
    )

    assert "can't describe" in response.answer.casefold()


async def test_a_stopped_camera_reports_no_picture(tmp_path: Path) -> None:
    del tmp_path
    camera = MockCamera()  # never started
    agent = await build(camera, StubVision())

    response = await agent.answer(
        AgentQuery(text="what do you see"), privacy=PrivacyState.PRIVATE_IDLE
    )

    assert "picture" in response.answer.casefold()


async def test_disabling_the_camera_stops_the_lens_not_just_a_flag() -> None:
    """The privacy switch must reach the hardware, not only the snapshot."""
    from manny.config import Settings
    from manny.lifecycle import build_services
    from manny.state import RuntimeState

    services = build_services(
        Settings(environment="test", mcp_mode="mock", _env_file=None)
    )
    await services.start()
    try:
        assert services.hardware.camera.running is True  # type: ignore[attr-defined]
        assert await services.hardware.camera.capture_frame() is not None

        await services.state.transition(
            RuntimeState.CAMERA_DISABLED, force=True, camera_enabled=False
        )

        assert services.hardware.camera.running is False  # type: ignore[attr-defined]
        assert await services.hardware.camera.capture_frame() is None
    finally:
        await services.stop()
