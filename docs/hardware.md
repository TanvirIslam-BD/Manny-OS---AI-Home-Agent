# Raspberry Pi Hardware Integration

Manny targets Raspberry Pi 5 8 GB on 64-bit Raspberry Pi OS. No final peripheral identifiers or GPIO mappings are encoded in source.

Device configuration includes `MANNY_AUDIO_DEVICE`, optional LED/display sysfs paths, camera privacy state, and the selected local STT/TTS/LLM backends.

Run `scripts/bootstrap_pi.sh` only after review. It verifies ARM64 Raspberry Pi hardware, asks for confirmation, installs prerequisites, and creates the service user. Run `scripts/install_app_pi.sh` from the reviewed source tree to copy Manny into `/opt/manny`, create its Python environment, and build the UI. Install `configs/raspberrypi.env.example` as `/opt/manny/.env` with mode `0600`, then replace its placeholder timezone and MCP endpoint. Next run `/opt/manny/scripts/install_gemma_pi.sh`; it builds pinned llama.cpp source and downloads the checksum-verified Gemma 3 1B IT Q4_K_M model after license confirmation. None of these scripts enables services. Run `scripts/verify_hardware.sh`, and explicitly install/enable `manny-llm`, `manny-core`, and `manny-kiosk` only after validation.

The default Pi inference budget is one 806 MB Q4_K_M model, a 4,096-token runtime context, four CPU threads, one inference slot, and a 5 GB systemd memory ceiling. These are safe starting values, not final performance claims; latency, thermals, memory, and power must be measured on the actual Pi 5 enclosure.

Physical selection remains for display/touch, camera FOV, microphone, acoustics, speaker/amplifier, LED controller, controls, GPIO, privacy wiring, power, thermal behavior, and enclosure.
