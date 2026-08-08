# Raspberry Pi Hardware Integration

Manny targets Raspberry Pi 5 8 GB on 64-bit Raspberry Pi OS. No final peripheral identifiers or GPIO mappings are encoded in source.

Device configuration includes `MANNY_AUDIO_DEVICE`, optional LED/display sysfs paths, camera privacy state, and the selected local STT/TTS/LLM backends.

Run `scripts/bootstrap_pi.sh` only after review. It verifies ARM64 Raspberry Pi hardware, asks for confirmation, installs prerequisites, and creates the service user. Run `scripts/install_app_pi.sh` from the reviewed source tree to copy Manny into `/opt/manny`, create its Python environment, and build the UI. Install `configs/raspberrypi.env.example` as `/opt/manny/.env` with mode `0600`, then replace its placeholder timezone and MCP endpoint. Next run `/opt/manny/scripts/install_gemma_pi.sh` and `scripts/install_multilingual_voice_pi.sh`; they build pinned llama.cpp and whisper.cpp source, download checksum-verified Gemma 3 1B IT Q4_K_M and multilingual Whisper base models, and install eSpeak NG. None of these scripts enables services. Run `scripts/verify_hardware.sh`, and explicitly install/enable `manny-llm`, `manny-core`, and `manny-kiosk` only after validation.

The default Pi inference budget is one 806 MB Q4_K_M language model, a 148 MB multilingual Whisper model, a 4,096-token runtime context, four CPU threads, one language-model inference slot, and a 5 GB systemd memory ceiling. These are safe starting values, not final performance claims; simultaneous STT, LLM, TTS, camera, latency, thermals, memory, and power must be measured on the actual Pi 5 enclosure.

Physical selection remains for display/touch, camera FOV, microphone, acoustics, speaker/amplifier, LED controller, controls, GPIO, privacy wiring, power, thermal behavior, and enclosure.
