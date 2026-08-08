# Manny OS Roadmap

## Phase 0 — Scaffold (current)

- [x] Monorepo and development configuration
- [x] Structured logging and typed settings
- [x] Authoritative runtime state model
- [x] Mock hardware adapters
- [x] FastAPI local service and WebSocket event bus
- [x] Responsive React/Vite browser simulator
- [x] Unit and API test infrastructure
- [x] Development and CI commands

Hardware-backed behavior is not part of this phase.

## Phase 1 — UI

- [ ] Complete accessibility and touch-target review on the selected display
- [ ] Confirmation, pairing, and settings screens
- [ ] Production motion and sound design
- [ ] Visual regression and component tests

## Phase 2 — Mock MCP + Agent

- [x] Official MCP SDK v2 Streamable HTTP adapter and remote tool discovery
- [ ] Mock Money Copilot server
- [ ] Deterministic tool policy and broker
- [ ] Swappable local model adapter and structured tool loop
- [ ] Budget, spending, and recurring-payment typed query flows

## Phase 3 — Voice

- [ ] Local wake word, VAD, STT, and TTS adapters
- [ ] Half-duplex interaction coordinator

## Phase 4 — Real MCP

- [x] OAuth discovery, PKCE authorization, token refresh/storage, and Streamable HTTP connection
- [ ] Production secure-token adapter and device pairing UX validation
- [ ] Offline cache and last-sync behavior

## Phase 5 — Vision

- [ ] Picamera2 adapter and local presence detection
- [ ] Multiple-person privacy behavior

## Phase 6 — Proactive intelligence

- [ ] Deterministic alert scheduler, quiet hours, cooldowns, and reminders

## Phase 7 — Device integration

- [ ] Display, audio, LED, controls, systemd, and Raspberry Pi validation

## Phase 8 — Hardening

- [ ] Secure provisioning, reset, redaction, signed updates, and production tests
