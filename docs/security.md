# Security Architecture

- API is loopback-only and emits CSP, anti-framing, no-sniff, no-referrer, and no-store headers.
- Browser code never receives MCP credentials.
- OAuth data rests in an ignored mode-0600 file, written through a temporary file so a partial write cannot be read. The `production` environment additionally requires the OS keyring and refuses to start without it.
- The Raspberry Pi profile uses the file, not a vault, and this is deliberate. The device is headless and must restore its connection after a power cut unattended, so any vault would have to unlock itself, placing the unlocking secret on the same SD card as the tokens; Pi 5 has no TPM to bind it to instead. Anyone holding the card or root on the device can therefore read Money Copilot refresh tokens. Treat physical possession of the device as equivalent to possession of its Money Copilot session, and revoke server-side after a loss rather than relying on on-device protection.
- Selecting keyring storage probes the vault at startup and refuses to run when none answers, because a missing vault used to surface only partway through authorization.
- Logs redact bearer credentials, OAuth codes/state, tokens, and client secrets; access logs are disabled.
- Tool calls are deny-by-default, allowlisted, schema-validated, and policy-evaluated.
- Unknown or multiple people cannot receive private finance results without authentication.
- Factory reset requires the exact phrase, clears OAuth/cache/reminders, and returns to locked pairing.
- CI scans secrets, audits dependencies, and runs test/build gates.
- Release archives carry SHA-256 checksums. Production requires Minisign signing and verification before installation.

Operators provision keyring and signing keys outside Git and validate the selected backend on the target OS.
