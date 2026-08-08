"""Check the local Manny Core health endpoint."""

from __future__ import annotations

import json
import urllib.request


def main() -> None:
    with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=3) as response:
        print(json.dumps(json.load(response), indent=2))


if __name__ == "__main__":
    main()
