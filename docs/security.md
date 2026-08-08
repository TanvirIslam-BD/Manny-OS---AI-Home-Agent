# Security Architecture

- API is loopback-only and emits CSP, anti-framing, no-sniff, no-referrer, and no-store headers.
- Browser code never receives MCP credentials.
- Development OAuth data uses an ignored mode-0600 file; production requires the OS keyring.
- Logs redact bearer credentials, OAuth codes/state, tokens, and client secrets; access logs are disabled.
- Tool calls are deny-by-default, allowlisted, schema-validated, and policy-evaluated.
- Unknown or multiple people cannot receive private finance results without authentication.
- Factory reset requires the exact phrase, clears OAuth/cache/reminders, and returns to locked pairing.
- CI scans secrets, audits dependencies, and runs test/build gates.
- Release archives carry SHA-256 checksums. Production requires Minisign signing and verification before installation.

Operators provision keyring and signing keys outside Git and validate the selected backend on the target OS.
