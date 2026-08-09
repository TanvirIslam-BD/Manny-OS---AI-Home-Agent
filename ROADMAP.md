# Manny OS Roadmap

## Software phase status

- [x] Phase 0 — scaffold, configuration, state, mocks, API, simulator, CI
- [x] Phase 1 — all UI states, pairing, confirmation, settings, accessibility, component tests
- [x] Phase 2 — mock MCP, policy broker, Ollama-served agent adapter, typed finance flows
- [x] Phase 3 — wake/VAD/STT/TTS, multilingual Whisper/eSpeak and Moonshine/Kokoro adapters, half-duplex desktop voice
- [x] Phase 4 — OAuth remote MCP, schema normalization, keyring storage, offline cache
- [x] Phase 5 — Picamera2 lifecycle, local presence, desktop camera, multi-person privacy
- [x] Phase 6 — reminders, scheduler, quiet hours, presence delivery, cooldowns
- [x] Phase 7 — configurable Pi adapters, systemd, bootstrap, hardware verifier
- [x] Phase 8 — reset, redaction, metrics, security CI, signed-update workflow

## External validation gates

- [ ] Select the final display, camera, microphone, speaker/amplifier, LED controller, controls, and GPIO mapping.
- [ ] Benchmark multilingual Whisper base, eSpeak NG, `gemma4:e2b`, and the person detector together on Raspberry Pi 5 8 GB, including English, Bangla, Hindi, Mandarin Chinese, and Japanese acceptance samples.
- [ ] Run `scripts/verify_hardware.sh` and physical camera/audio/display/privacy tests.
- [ ] Validate touch, motion, acoustics, wake-word errors, thermal behavior, and power recovery on-device.
- [ ] Provision the production OS keyring, OAuth policy, Minisign signing key, and public verification key.
- [ ] Obtain a Money Copilot recurring-payment tool contract. The current server does not advertise one, so Manny refuses to invent that data.
- [ ] Enable systemd services only after device configuration passes validation.

The desktop simulator and automated suites are authoritative until physical and operational gates are available.
