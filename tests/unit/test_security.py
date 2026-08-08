import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from manny.config import Settings
from manny.main import create_app
from manny.observability.logging import JsonFormatter, redact


def test_log_redaction_removes_tokens_and_oauth_codes() -> None:
    message = "Authorization: Bearer abc.def access_token=secret code=oauth-code"
    redacted = redact(message)
    assert "abc.def" not in redacted
    assert "secret" not in redacted
    assert "oauth-code" not in redacted
    record = logging.LogRecord("manny", logging.INFO, __file__, 1, message, (), None)
    payload = json.loads(JsonFormatter().format(record))
    assert "[REDACTED]" in payload["event"]


def test_security_headers_are_present(tmp_path: Path) -> None:
    app = create_app(
        Settings(environment="test", mcp_mode="mock", data_directory=tmp_path, _env_file=None)
    )
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_confirmed_reset_clears_local_reminders_and_locks_device(tmp_path: Path) -> None:
    app = create_app(
        Settings(environment="test", mcp_mode="mock", data_directory=tmp_path, _env_file=None)
    )
    with TestClient(app) as client:
        client.post(
            "/api/reminders",
            json={"title": "Temporary", "due_at": datetime.now(UTC).isoformat()},
        )
        response = client.post("/api/device/reset", json={"confirmation": "RESET MANNY"})
        reminders = client.get("/api/reminders")

    assert response.status_code == 200
    assert response.json()["state"] == "PAIRING"
    assert response.json()["privacy"] == "PRIVACY_LOCKED"
    assert reminders.json() == []


def test_reset_rejects_incorrect_confirmation(tmp_path: Path) -> None:
    app = create_app(
        Settings(environment="test", mcp_mode="mock", data_directory=tmp_path, _env_file=None)
    )
    with TestClient(app) as client:
        response = client.post("/api/device/reset", json={"confirmation": "yes"})
    assert response.status_code == 422
