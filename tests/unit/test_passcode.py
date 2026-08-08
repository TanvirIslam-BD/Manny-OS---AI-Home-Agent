"""Passcode unlock: the only thing that may produce a trusted session."""

from __future__ import annotations

from pathlib import Path

import pytest

from manny.security import LockedOutError, PasscodeError, PasscodeLock


async def test_passcode_is_hashed_and_never_stored_in_the_clear(tmp_path: Path) -> None:
    path = tmp_path / "passcode.json"
    lock = PasscodeLock(path)

    await lock.set_passcode("246813")

    stored = path.read_text(encoding="utf-8")
    assert "246813" not in stored
    assert "salt" in stored and "hash" in stored


async def test_unlock_requires_the_correct_passcode(tmp_path: Path) -> None:
    lock = PasscodeLock(tmp_path / "passcode.json")
    await lock.set_passcode("246813")
    await lock.lock()

    assert lock.is_unlocked() is False
    with pytest.raises(PasscodeError):
        await lock.unlock("111111")
    assert lock.is_unlocked() is False

    status = await lock.unlock("246813")
    assert status.unlocked is True
    assert lock.is_unlocked() is True


async def test_repeated_failures_lock_the_device_out(tmp_path: Path) -> None:
    lock = PasscodeLock(tmp_path / "passcode.json")
    await lock.set_passcode("246813")
    await lock.lock()

    for _ in range(5):
        with pytest.raises(PasscodeError):
            await lock.unlock("000000")

    # A brute force of a short numeric PIN must not be free.
    with pytest.raises(LockedOutError):
        await lock.unlock("246813")


async def test_changing_a_passcode_requires_the_current_one(tmp_path: Path) -> None:
    lock = PasscodeLock(tmp_path / "passcode.json")
    await lock.set_passcode("246813")

    with pytest.raises(PasscodeError):
        await lock.set_passcode("135790", current="999999")

    await lock.set_passcode("135790", current="246813")
    await lock.lock()
    assert (await lock.unlock("135790")).unlocked is True


async def test_weak_passcodes_are_rejected(tmp_path: Path) -> None:
    lock = PasscodeLock(tmp_path / "passcode.json")

    for candidate in ("12", "abcd", "1111"):
        with pytest.raises(PasscodeError):
            await lock.set_passcode(candidate)


async def test_session_expires(tmp_path: Path) -> None:
    lock = PasscodeLock(tmp_path / "passcode.json", session_seconds=0)
    await lock.set_passcode("246813")

    # A zero-length session is already over, so privacy re-engages immediately.
    assert lock.is_unlocked() is False
