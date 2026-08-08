# Security Architecture

The local API binds to loopback, public settings omit MCP endpoints and credentials, and hardware access is isolated behind adapters. MCP OAuth tokens stay in the host runtime and are never exposed to browser JavaScript or agent context. Raw HTTP access logs are disabled so the OAuth callback's short-lived authorization code is not recorded. Development storage uses a Git-ignored restrictive file; production secure storage, reset, broader log-redaction verification, and signed updates remain tracked for hardening.
