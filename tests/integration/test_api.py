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


def test_camera_disabled_rejects_presence_and_preserves_privacy_lock() -> None:
    with build_client() as client:
        client.post("/api/simulator/presence", json={"people_count": 2})
        client.post("/api/privacy/lock")
        disabled = client.post(
            "/api/simulator/state",
            json={"state": "CAMERA_DISABLED"},
        )
        presence = client.post(
            "/api/simulator/presence",
            json={"people_count": 1},
        )
        current = client.get("/api/state")

    assert disabled.status_code == 200
    assert disabled.json()["state"] == "CAMERA_DISABLED"
    assert disabled.json()["camera_enabled"] is False
    assert disabled.json()["presence"] is False
    assert disabled.json()["people_count"] == 0
    assert disabled.json()["privacy"] == "PRIVACY_LOCKED"
    assert presence.status_code == 409
    assert presence.json()["detail"] == "camera is disabled"
    assert current.json() == disabled.json()


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


def test_switch_account_clears_account_state_without_factory_reset() -> None:
    with build_client() as client:
        response = client.post("/api/mcp/switch-account")
        metrics = client.get("/api/metrics")

    assert response.status_code == 200
    assert response.json()["phase"] == "mock"
    assert "token" not in response.text.lower()
    assert metrics.json()["mcp_account_switches"] == 1


def test_duplicate_oauth_callback_is_idempotent_when_connected() -> None:
    with build_client() as client:
        response = client.get(
            "/api/mcp/oauth/callback?code=duplicate&state=duplicate",
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/?mcp=connected"


def test_listening_toggle_is_rejected_without_a_device_microphone() -> None:
    with build_client() as client:
        state = client.get("/api/state")
        response = client.post("/api/device/listening", json={"enabled": True})

    assert state.json()["listening_available"] is False
    assert response.status_code == 409
    assert response.json()["detail"] == "the device listen loop is unavailable"


def test_device_language_is_applied_and_broadcast() -> None:
    with build_client() as client:
        response = client.post("/api/device/language", json={"language": "bn-BD"})
        current = client.get("/api/state")
        auto = client.post("/api/device/language", json={"language": "auto"})
        rejected = client.post("/api/device/language", json={"language": "not a tag!"})

    assert response.status_code == 200
    assert response.json()["language"] == "bn-BD"
    assert current.json()["language"] == "bn-BD"
    assert auto.json()["language"] == "auto"
    assert rejected.status_code == 422


def test_client_cannot_assert_authentication_to_bypass_the_privacy_gate() -> None:
    with build_client() as client:
        client.post("/api/simulator/presence", json={"people_count": 2})
        spoofed = client.post(
            "/api/agent/query",
            json={"text": "How is my budget?", "authenticated": True},
        )

    # The flag is advisory; only a verified unlock session may open the gate.
    assert spoofed.status_code == 200
    assert spoofed.json()["requires_authentication"] is True


def test_passcode_unlock_opens_the_gate_and_locking_closes_it() -> None:
    with build_client() as client:
        client.post("/api/simulator/presence", json={"people_count": 2})
        blocked = client.post("/api/agent/query", json={"text": "How is my budget?"})

        client.post("/api/security/passcode", json={"passcode": "246813"})
        client.post("/api/security/lock")
        rejected = client.post("/api/security/unlock", json={"passcode": "000000"})
        unlocked = client.post("/api/security/unlock", json={"passcode": "246813"})
        state = client.get("/api/state")
        allowed = client.post("/api/agent/query", json={"text": "How is my budget?"})

        client.post("/api/security/lock")
        relocked = client.post("/api/agent/query", json={"text": "How is my budget?"})

    assert blocked.json()["requires_authentication"] is True
    assert rejected.status_code == 401
    assert unlocked.json()["unlocked"] is True
    # A verified session is the only producer of PRESENT_TRUSTED.
    assert state.json()["privacy"] == "PRESENT_TRUSTED"
    assert allowed.json()["requires_authentication"] is False
    assert "spent" in allowed.json()["answer"].casefold()
    assert relocked.json()["requires_authentication"] is True
