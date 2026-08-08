"""Fail CI on credential-shaped content in tracked source files."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PATTERNS = [
    re.compile(
        r"(?i)(access_token|refresh_token|client_secret)[ \t]*[=:][ \t]*"
        r"['\"][A-Za-z0-9._~-]{16,}['\"]"
    ),
    re.compile(r"(?im)^[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD)=\S{16,}$"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
ALLOW = {"scripts/check_secrets.py", "tests/unit/test_security.py"}


def main() -> int:
    tracked = subprocess.run(
        ["git", "ls-files"], check=True, capture_output=True, text=True
    ).stdout.splitlines()
    findings: list[str] = []
    for name in tracked:
        if name in ALLOW:
            continue
        path = Path(name)
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(pattern.search(text) for pattern in PATTERNS):
            findings.append(name)
    if findings:
        print("Potential secrets detected in tracked files:", *findings, sep="\n")
        return 1
    print("No credential-shaped content detected in tracked source files.")
    return 0


raise SystemExit(main())
