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
- Accessible pairing, confirmation, settings, conversation, desktop voice, and private camera simulation
- Mock MCP server, policy broker, typed finance contracts, and remote schema normalization
- Half-duplex voice with optional Moonshine STT and Kokoro TTS adapters
- Timestamped offline cache and OS-keyring token storage
- Presence privacy, persistent reminders, quiet hours, and alert cooldowns
- Configurable Pi adapters, systemd, bootstrap, and hardware verification
- Reset, redaction, security headers, metrics, security CI, and signed-update verification
- Live MCP-backed device cards, persistent MCP sessions, request coalescing, and verified-data refresh controls
- Gemma 3 1B IT llama.cpp adapter, short conversational context, schema-validated routing, deterministic fallback, and hardened Pi model service

### Security

- Loopback-only API defaults
- Secret and local-data exclusions
- Face recognition disabled by default
- MCP tokens excluded from API responses, logs, Git, and browser JavaScript
- Production token storage requires the OS credential vault
- Production updates require checksum and signature verification
