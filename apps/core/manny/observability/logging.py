"""Structured JSON logging without sensitive request payloads."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "event": redact(record.getMessage()),
        }
        for key in ("request_id", "tool_name", "latency_ms", "success"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


_SENSITIVE = re.compile(
    r"(?i)(access_token|refresh_token|client_secret|authorization|code|state)"
    r"([\s=:]+)([^\s&,}\"]+)"
)
_BEARER = re.compile(r"(?i)bearer\s+[a-z0-9._~+/-]+")


def redact(value: str) -> str:
    value = _BEARER.sub("Bearer [REDACTED]", value)
    return _SENSITIVE.sub(r"\1\2[REDACTED]", value)
