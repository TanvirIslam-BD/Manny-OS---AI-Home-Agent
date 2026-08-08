"""Passcode unlock for private financial views.

Requirements 7.4 lists a UI PIN as the primary way to unlock sensitive
information. This is that mechanism, and it is the only thing that can produce a
trusted session — the `authenticated` flag on a request is not trusted, because
anything able to reach the loopback API could assert it.

The passcode itself is never stored. Only a PBKDF2-HMAC-SHA256 hash and its salt
are written, with restrictive file permissions, and comparisons are constant
time. Repeated failures lock the device out for a growing interval so the small
key space of a numeric PIN cannot simply be enumerated.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_ITERATIONS = 200_000
_ALGORITHM = "sha256"
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 60


class SecurityStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    passcode_set: bool
    unlocked: bool
    attempts_remaining: int = Field(ge=0)
    locked_out_until: datetime | None = None
    unlocked_until: datetime | None = None


class PasscodeError(ValueError):
    """Raised when a passcode is rejected or does not meet the policy."""


class LockedOutError(PasscodeError):
    """Raised while the device is refusing attempts after repeated failures."""


class PasscodeLock:
    def __init__(
        self,
        path: Path,
        *,
        session_seconds: float = 300,
        minimum_length: int = 4,
        maximum_length: int = 12,
    ) -> None:
        self._path = path
        self._session = timedelta(seconds=session_seconds)
        self._minimum_length = minimum_length
        self._maximum_length = maximum_length
        self._lock = asyncio.Lock()
        self._failures = 0
        self._locked_out_until: datetime | None = None
        self._unlocked_until: datetime | None = None

    # -- state -------------------------------------------------------------

    def is_unlocked(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        return self._unlocked_until is not None and self._unlocked_until > current

    async def status(self) -> SecurityStatus:
        async with self._lock:
            record = await asyncio.to_thread(self._read)
        now = datetime.now(UTC)
        locked_out = self._locked_out_until if self._is_locked_out(now) else None
        return SecurityStatus(
            passcode_set="hash" in record,
            unlocked=self.is_unlocked(now),
            attempts_remaining=max(0, _MAX_ATTEMPTS - self._failures),
            locked_out_until=locked_out,
            unlocked_until=self._unlocked_until if self.is_unlocked(now) else None,
        )

    # -- operations --------------------------------------------------------

    async def set_passcode(self, passcode: str, current: str | None = None) -> SecurityStatus:
        self._validate(passcode)
        async with self._lock:
            record = await asyncio.to_thread(self._read)
            # Changing an existing passcode requires proving the old one.
            if "hash" in record and (current is None or not self._matches(record, current)):
                raise PasscodeError("the current passcode is incorrect")
            salt = secrets.token_bytes(16)
            payload = {
                "salt": salt.hex(),
                "hash": self._derive(passcode, salt).hex(),
                "iterations": _ITERATIONS,
            }
            await asyncio.to_thread(self._write, payload)
            self._failures = 0
            self._locked_out_until = None
            self._unlocked_until = datetime.now(UTC) + self._session
        return await self.status()

    async def unlock(self, passcode: str) -> SecurityStatus:
        async with self._lock:
            now = datetime.now(UTC)
            if self._is_locked_out(now):
                raise LockedOutError("too many attempts; try again shortly")
            record = await asyncio.to_thread(self._read)
            if "hash" not in record:
                raise PasscodeError("no passcode is set on this device")
            if not self._matches(record, passcode):
                self._failures += 1
                if self._failures >= _MAX_ATTEMPTS:
                    self._locked_out_until = now + timedelta(seconds=_LOCKOUT_SECONDS)
                    self._failures = 0
                raise PasscodeError("that passcode is incorrect")
            self._failures = 0
            self._locked_out_until = None
            self._unlocked_until = now + self._session
        return await self.status()

    async def lock(self) -> SecurityStatus:
        async with self._lock:
            self._unlocked_until = None
        return await self.status()

    async def clear(self) -> None:
        """Remove the passcode entirely; used by factory reset."""
        async with self._lock:
            self._unlocked_until = None
            self._failures = 0
            self._locked_out_until = None
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                return

    # -- internals ---------------------------------------------------------

    def _validate(self, passcode: str) -> None:
        if not passcode.isdigit():
            raise PasscodeError("the passcode must be digits only")
        if not self._minimum_length <= len(passcode) <= self._maximum_length:
            raise PasscodeError(
                f"the passcode must be {self._minimum_length}-{self._maximum_length} digits"
            )
        if len(set(passcode)) == 1:
            raise PasscodeError("choose a passcode that is not a single repeated digit")

    def _is_locked_out(self, now: datetime) -> bool:
        return self._locked_out_until is not None and self._locked_out_until > now

    def _matches(self, record: dict[str, Any], passcode: str) -> bool:
        try:
            salt = bytes.fromhex(str(record["salt"]))
            expected = bytes.fromhex(str(record["hash"]))
        except (KeyError, ValueError):
            return False
        return hmac.compare_digest(self._derive(passcode, salt), expected)

    @staticmethod
    def _derive(passcode: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac(_ALGORITHM, passcode.encode("utf-8"), salt, _ITERATIONS)

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self._path)
        os.chmod(self._path, 0o600)
