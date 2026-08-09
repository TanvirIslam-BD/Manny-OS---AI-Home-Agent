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
- `POST /api/voice/speak`, which synthesises a reply the browser has no voice for and returns it as WAV, so the desktop simulator speaks the languages its host operating system cannot
- The simulator now speaks a streamed reply sentence by sentence as it is written, which is what the device has always done and the desktop never did. Sentences arrive faster than they can be spoken and both playback paths are asynchronous, so each is chained behind the one before it and every step waits for audio to stop rather than to start; without that they play over each other. A reply spoken this way is not repeated whole at the end, the same branch the voice coordinator takes after a streamed turn. Starting a new question, or picking up the microphone, silences whatever is still queued — the half-duplex rule the device enforces with its turn lock
- Typed replies stream sentence by sentence over the existing WebSocket as `agent.reply_chunk`, and the simulator shows them as they arrive. Streaming already existed but only the voice coordinator ever passed a listener, so typing was the slowest path in the product. Measured warm on a desktop CPU: first sentence in 3.3–5.8 s against 5.1–8.4 s for the whole reply, a 31–57% cut in perceived latency, largest on the longest answers. Finance replies are deliberately excluded — they come from validated MCP data in milliseconds, and a half-rendered figure is worse than a wait

### Changed

- The local model is served by Ollama instead of llama.cpp, and the conversational model is `gemma3n:e2b` — one multimodal model for text and image, replacing both the 1B router and the separate 4B vision model on its own server (ADR-020)
- `install_gemma_pi.sh`, the two Windows llama.cpp scripts and `manny-llm.service` are gone; `install_ollama_pi.sh` installs a checksum-verified runtime and applies Manny's hardening as a drop-in over Ollama's own unit
- Model weights are no longer checksum-pinned, because Ollama's registry offers no equivalent; the runtime binary still is, since a service binary is code rather than data
- The target device is a Raspberry Pi 5 8 GB **with NVMe** (ADR-021), and the default model is chosen to fit it: `gemma3n:e2b` at 5.24 GB fits the ~6.3 GB available, where `gemma4:e2b` at 6.67 GB exceeds it and can only run partially resident - a documented one-variable switch once measured. The model file is larger than the RAM left for it, so mmap is load-bearing: the installer configures zram and swappiness so the page cache keeps the weights, disables SD-card swap, warns when the model store is not on NVMe, and bring-up fails if it is not
- The Ollama drop-in bounds the KV cache deliberately: one parallel slot, a 3,072-token context sized to Manny's measured prompt, and a q8_0 KV cache behind flash attention. Device profiles also carry four turns of history rather than six, since retrieval covers what falls out of the window
- `docs/hardware.md` documents the 8 GB memory budget, what the configuration already does about it, and the ordered levers left — zram, dropping the kiosk, then more memory or a smaller tag
- No systemd memory ceiling is set for the model: an E2B-class model's resident size depends on whether the runtime offloads per-layer embeddings, and a guessed ceiling either does nothing or OOM-kills it long after deployment
- `llm_max_tokens` drops from 320 to 160 in every profile. Decode measured 16 tok/s on a desktop Ryzen 5600G with no GPU offload, and Google's published figure for this model class on a Pi 5 is 8 tok/s, so the old ceiling allowed a 20-second reply on a workstation and 40 on the device — longer than anyone waits for a companion to finish a sentence. It is not cut further because the device's default language is Bengali, whose script costs more tokens per word in this tokenizer than English, so a cap that reads as generous in English truncates in bn-BD
- `MANNY_ESPEAK_NG_BINARY` falls back to whatever `espeak-ng` is on PATH when the configured path does not exist, so one profile covers the Pi's `/usr/bin/espeak-ng` and a desktop install anywhere else. An unresolvable name is passed through unchanged rather than substituted, so synthesis still fails loudly instead of speaking with some other program

### Fixed

- Pi and production profiles asked for `gemma-3-4b-it` while the installer downloaded the 1B model, so `manny-llm` exited on a missing file after a default install
- `manny-llm.service` now launches the model the installer recorded in `/opt/manny/model.env` instead of a hardcoded filename that could drift from what is on disk
- Hardware verification accepts either quantisation, checks the recorded model against the one present on disk, and confirms the running server answers to the alias the core sends
- Pi and production profiles pointed scene description at port 8080, the text model's server, which cannot read a frame; both now use 8081 as `Settings` already defaulted to
- Replies in most of the languages Manny supports were displayed and never spoken on the desktop, because browser speech only has the voices the host operating system installed and a default Windows install ships English only. The simulator now falls back to the device's own synthesiser, and only reports that a reply cannot be spoken when that fails too — naming both what the browser lacks and what the device said

### Security

- Loopback-only API defaults
- Secret and local-data exclusions
- Face recognition disabled by default
- MCP tokens excluded from API responses, logs, Git, and browser JavaScript
- Production token storage requires the OS credential vault, and selecting it now probes the vault at startup instead of accepting any module that merely exposes the API, so a host without one fails immediately rather than partway through authorization
- On-device token exposure is stated rather than implied: the Pi keeps OAuth material in a mode-0600 file because a headless appliance cannot hold a vault key anywhere it cannot itself reach, so physical possession of the device is possession of the Money Copilot session and loss is handled by server-side revocation (ADR-013)
- Production updates require checksum and signature verification
