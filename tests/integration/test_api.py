from fastapi.testclient import TestClient

from manny.config import Settings
from manny.main import create_app


def build_client() -> TestClient:
    app = create_app(
        Settings(
            environment="test",
            config_profile="development",
            mcp_mode="mock",
            _env_file=None,
        )
    )
    return TestClient(app)


def test_health_and_initial_state() -> None:
    with build_client() as client:
        health = client.get("/api/health")
        state = client.get("/api/state")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert state.json()["state"] == "IDLE"


def test_simulator_state_is_broadcast() -> None:
    with build_client() as client, client.websocket_connect("/api/ws") as websocket:
        initial = websocket.receive_json()
        response = client.post("/api/simulator/state", json={"state": "THINKING"})
        event = websocket.receive_json()

    assert initial["type"] == "system.state"
    assert response.status_code == 200
    assert event["payload"]["state"] == "THINKING"


def test_multiple_people_privacy() -> None:
    with build_client() as client:
        response = client.post("/api/simulator/presence", json={"people_count": 2})

    assert response.status_code == 200
    assert response.json()["privacy"] == "MULTIPLE_PEOPLE"


def test_offline_health_is_degraded() -> None:
    with build_client() as client:
        client.post("/api/simulator/connectivity", json={"connected": False})
        response = client.get("/api/health")

    assert response.json()["status"] == "degraded"
    assert response.json()["components"]["money_mcp"] == "offline"


def test_mock_mcp_status_contains_no_credentials() -> None:
    with build_client() as client:
        response = client.get("/api/mcp/status")

    assert response.status_code == 200
    assert response.json()["phase"] == "mock"
    assert "token" not in response.text.lower()


def test_duplicate_oauth_callback_is_idempotent_when_connected() -> None:
    with build_client() as client:
        response = client.get(
            "/api/mcp/oauth/callback?code=duplicate&state=duplicate",
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/?mcp=connected"
