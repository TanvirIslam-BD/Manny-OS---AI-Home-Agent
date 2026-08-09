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
- Multilingual text and voice pipeline with BCP-47 metadata, same-language safe finance templates, whisper.cpp automatic STT detection, eSpeak NG output, browser language controls, and Pi installation
- Selectable Gemma quantisation via `MANNY_GEMMA_QUANT`, with `q4_0` available for faster Cortex-A76 prompt processing once you supply a checksum you verified

### Changed

- The local model is served by Ollama instead of llama.cpp, and the conversational model is `gemma4:e2b` — one multimodal model for text and image, replacing both the 1B router and the separate 4B vision model on its own server (ADR-020)
- `install_gemma_pi.sh`, the two Windows llama.cpp scripts and `manny-llm.service` are gone; `install_ollama_pi.sh` installs a checksum-verified runtime and applies Manny's hardening as a drop-in over Ollama's own unit
- Model weights are no longer checksum-pinned, because Ollama's registry offers no equivalent; the runtime binary still is, since a service binary is code rather than data
- The target device is a Raspberry Pi 5 8 GB **with NVMe** (ADR-021). The model file is larger than the RAM left for it, so mmap is load-bearing: the installer configures zram and swappiness so the page cache keeps the weights, disables SD-card swap, warns when the model store is not on NVMe, and bring-up fails if it is not
- The Ollama drop-in bounds the KV cache deliberately: one parallel slot, a 3,072-token context sized to Manny's measured prompt, and a q8_0 KV cache behind flash attention. Device profiles also carry four turns of history rather than six, since retrieval covers what falls out of the window
- `docs/hardware.md` documents the 8 GB memory budget, what the configuration already does about it, and the ordered levers left — zram, dropping the kiosk, then more memory or a smaller tag
- No systemd memory ceiling is set for the model: an E2B-class model's resident size depends on whether the runtime offloads per-layer embeddings, and a guessed ceiling either does nothing or OOM-kills it long after deployment

### Fixed

- Pi and production profiles asked for `gemma-3-4b-it` while the installer downloaded the 1B model, so `manny-llm` exited on a missing file after a default install
- `manny-llm.service` now launches the model the installer recorded in `/opt/manny/model.env` instead of a hardcoded filename that could drift from what is on disk
- Hardware verification accepts either quantisation, checks the recorded model against the one present on disk, and confirms the running server answers to the alias the core sends
- Pi and production profiles pointed scene description at port 8080, the text model's server, which cannot read a frame; both now use 8081 as `Settings` already defaulted to

### Security

- Loopback-only API defaults
- Secret and local-data exclusions
- Face recognition disabled by default
- MCP tokens excluded from API responses, logs, Git, and browser JavaScript
- Production token storage requires the OS credential vault, and selecting it now probes the vault at startup instead of accepting any module that merely exposes the API, so a host without one fails immediately rather than partway through authorization
- On-device token exposure is stated rather than implied: the Pi keeps OAuth material in a mode-0600 file because a headless appliance cannot hold a vault key anywhere it cannot itself reach, so physical possession of the device is possession of the Money Copilot session and loss is handled by server-side revocation (ADR-013)
- Production updates require checksum and signature verification
