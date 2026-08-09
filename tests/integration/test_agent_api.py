import pytest
from fastapi.testclient import TestClient

from manny.agent import AgentDecision
from manny.config import Settings
from manny.main import create_app


def test_budget_question_executes_mock_tool_and_returns_validated_answer() -> None:
    app = create_app(Settings(environment="test", mcp_mode="mock", _env_file=None))
    with TestClient(app) as client:
        response = client.post("/api/agent/query", json={"text": "How's my budget?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_name"] == "money.get_budget_summary"
    assert "$560.00 remaining" in payload["answer"]
    assert payload["data"]["budget"] == 1800


def test_budget_question_is_private_when_multiple_people_are_present() -> None:
    app = create_app(Settings(environment="test", mcp_mode="mock", _env_file=None))
    with TestClient(app) as client:
        client.post("/api/simulator/presence", json={"people_count": 2})
        response = client.post("/api/agent/query", json={"text": "How's my budget?"})

    assert response.status_code == 200
    assert response.json()["requires_authentication"] is True
    assert response.json()["data"] is None


def test_simulated_voice_budget_turn_returns_spoken_answer() -> None:
    app = create_app(Settings(environment="test", mcp_mode="mock", _env_file=None))
    with TestClient(app) as client:
        response = client.post("/api/interaction/voice/simulate", json={"text": "How's my budget?"})

    assert response.status_code == 200
    assert response.json()["transcript"] == "How's my budget?"
    assert "$560.00 remaining" in response.json()["answer"]


def test_simulated_voice_preserves_selected_language() -> None:
    app = create_app(Settings(environment="test", mcp_mode="mock", _env_file=None))
    with TestClient(app) as client:
        response = client.post(
            "/api/interaction/voice/simulate",
            json={"text": "আমার বাজেট", "language": "bn-BD"},
        )

    assert response.status_code == 200
    assert response.json()["language"] == "bn-BD"


def test_agent_rejects_invalid_language_hint() -> None:
    app = create_app(Settings(environment="test", mcp_mode="mock", _env_file=None))
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/query",
            json={"text": "Hello", "language": "en\nignore-rules"},
        )

    assert response.status_code == 422


class _StreamingIntentModel:
    """Stands in for the Ollama model so streaming can be tested without one."""

    @property
    def status(self) -> str:
        return "stub"

    async def decide(
        self,
        text: str,
        history: list[object],
        language_hint: str | None = None,
        on_reply_chunk: object | None = None,
    ) -> AgentDecision:
        del text, history
        pieces = ["First sentence. ", "Second sentence."]
        if on_reply_chunk is not None:
            for piece in pieces:
                await on_reply_chunk(piece)  # type: ignore[operator]
        return AgentDecision(
            intent="general", reply="".join(pieces), language=language_hint or "en"
        )


def build_streaming_client(
    monkeypatch: pytest.MonkeyPatch, *, streaming: bool
) -> TestClient:
    monkeypatch.setattr(
        "manny.lifecycle.OllamaAgentModel",
        lambda **_kwargs: _StreamingIntentModel(),
    )
    return TestClient(
        create_app(
            Settings(
                environment="test",
                mcp_mode="mock",
                llm_backend="ollama",
                llm_stream_replies=streaming,
                _env_file=None,
            )
        )
    )


def test_a_typed_reply_is_published_sentence_by_sentence_while_it_is_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Streaming existed but only the voice coordinator passed a listener, so a typed
    # question waited for the whole reply — the worst case in the product, since
    # decode runs at roughly 16 tok/s on a desktop CPU and half that on the device.
    with (
        build_streaming_client(monkeypatch, streaming=True) as client,
        client.websocket_connect("/api/ws") as websocket,
    ):
        websocket.receive_json()  # opening state frame
        response = client.post("/api/agent/query", json={"text": "tell me a joke"})
        frames = [websocket.receive_json() for _ in range(4)]

    assert response.status_code == 200
    published = [f["payload"] for f in frames if f["type"] == "agent.reply_chunk"]
    assert [p["text"] for p in published] == ["First sentence. ", "Second sentence."]
    # Tagged with the question's language, because the reply's own language field
    # arrives only when the reply ends — and a client that cannot pick a voice until
    # then is back to waiting for the whole thing.
    assert all(p["language"] for p in published)
    # The face stops thinking once there is something to say, not at the end.
    speaking = [
        f for f in frames
        if f["type"] == "system.state" and f["payload"]["state"] == "SPEAKING"
    ]
    assert speaking, "the device stayed in THINKING while it was already answering"


def test_finance_answers_are_not_streamed_because_they_arrive_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Finance replies are built from validated MCP data in milliseconds. Streaming a
    # partial figure would put a truncated amount on screen, which is worse than a wait.
    with (
        build_streaming_client(monkeypatch, streaming=True) as client,
        client.websocket_connect("/api/ws") as websocket,
    ):
        websocket.receive_json()
        response = client.post("/api/agent/query", json={"text": "How's my budget?"})
        frames = [websocket.receive_json() for _ in range(2)]

    assert response.json()["tool_name"] == "money.get_budget_summary"
    assert not [f for f in frames if f["type"] == "agent.reply_chunk"]


def test_streaming_stays_off_when_the_profile_disables_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with (
        build_streaming_client(monkeypatch, streaming=False) as client,
        client.websocket_connect("/api/ws") as websocket,
    ):
        websocket.receive_json()
        response = client.post("/api/agent/query", json={"text": "tell me a joke"})
        frames = [websocket.receive_json() for _ in range(2)]

    assert response.status_code == 200
    assert not [f for f in frames if f["type"] == "agent.reply_chunk"]
