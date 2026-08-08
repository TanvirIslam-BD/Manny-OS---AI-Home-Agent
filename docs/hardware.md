# Raspberry Pi Hardware Integration

Manny targets Raspberry Pi 5 8 GB on 64-bit Raspberry Pi OS. No final peripheral identifiers or GPIO mappings are encoded in source.

Device configuration includes `MANNY_AUDIO_DEVICE`, optional LED/display sysfs paths, camera privacy state, and the selected local STT/TTS backends.

Run `scripts/bootstrap_pi.sh` only after review. It verifies ARM64 Raspberry Pi hardware, asks for confirmation, installs prerequisites, and creates the service user. It does not enable services. Run `scripts/verify_hardware.sh`, configure `/opt/manny/.env`, and explicitly install/enable the systemd units only after validation.

Physical selection remains for display/touch, camera FOV, microphone, acoustics, speaker/amplifier, LED controller, controls, GPIO, privacy wiring, power, thermal behavior, and enclosure.
