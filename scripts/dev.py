"""Run the API and Vite simulator together without a process manager dependency."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if npm is None:
        print("npm is required to run the Manny simulator", file=sys.stderr)
        return 1

    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "manny.main:app",
            "--app-dir",
            "apps/core",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--no-access-log",
            "--reload",
        ],
        cwd=ROOT,
    )
    ui = subprocess.Popen([npm, "run", "dev"], cwd=ROOT / "apps" / "ui")
    processes = (api, ui)

    def stop(_signum: int, _frame: object) -> None:
        for process in processes:
            process.terminate()

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)

    print("Manny Core: http://127.0.0.1:8765")
    print("Manny simulator: http://127.0.0.1:5173")
    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.25)
    finally:
        stop(0, object())
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    return next((process.returncode or 0 for process in processes if process.returncode), 0)


if __name__ == "__main__":
    raise SystemExit(main())
