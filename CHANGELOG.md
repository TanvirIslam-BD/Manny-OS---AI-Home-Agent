# Changelog

All notable changes to Manny OS are documented here.

## [Unreleased]

### Added

- Phase 0 monorepo scaffold
- FastAPI core with health, state, settings, simulator, and WebSocket interfaces
- Typed runtime state machine and mock hardware adapters
- Responsive React/Vite Manny simulator
- Official MCP Python SDK v2 Streamable HTTP client
- OAuth discovery, PKCE authorization callback, token refresh/storage, and connection UI
- MCP tool discovery with deny-by-default execution allowlisting
- Development commands, tests, and CI workflow

### Security

- Loopback-only API defaults
- Secret and local-data exclusions
- Face recognition disabled by default
- MCP tokens excluded from API responses, logs, Git, and browser JavaScript
