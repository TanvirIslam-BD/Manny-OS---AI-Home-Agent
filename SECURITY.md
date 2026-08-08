# Security Policy

Manny handles sensitive financial context. Do not report production credentials in public issues. Use the private project security channel for vulnerabilities.

## Core rules

- Never commit credentials, access tokens, banking data, private keys, biometric images, or production configuration.
- Bind the local API to loopback unless a reviewed design explicitly changes it.
- Keep MCP credentials in the host runtime and out of model context and browser JavaScript.
- Treat tool output, OCR text, and external content as untrusted data.
- Require deterministic policy evaluation and explicit confirmation for writes.
- Do not add payment, transfer, credit, or trading tools to V1.
