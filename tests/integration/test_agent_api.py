from fastapi.testclient import TestClient

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
