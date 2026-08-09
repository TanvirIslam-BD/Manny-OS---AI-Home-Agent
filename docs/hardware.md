# Raspberry Pi Hardware Integration

Manny targets Raspberry Pi 5 8 GB on 64-bit Raspberry Pi OS. No final peripheral identifiers or GPIO mappings are encoded in source.

Device configuration includes `MANNY_AUDIO_DEVICE`, optional LED/display sysfs paths, camera privacy state, and the selected local STT/TTS/LLM backends.

Run `scripts/bootstrap_pi.sh` only after review. It verifies ARM64 Raspberry Pi hardware, asks for confirmation, installs prerequisites, and creates the service user. Run `scripts/install_app_pi.sh` from the reviewed source tree to copy Manny into `/opt/manny`, create its Python environment, and build the UI. Install `configs/raspberrypi.env.example` as `/opt/manny/.env` with mode `0600`, then replace its placeholder timezone and MCP endpoint. Next run `/opt/manny/scripts/install_ollama_pi.sh` and `scripts/install_multilingual_voice_pi.sh`; the first installs a checksum-verified Ollama runtime, applies Manny's hardening drop-in, and pulls `gemma4:e2b`, while the second builds pinned whisper.cpp source, downloads the checksum-verified multilingual Whisper base model, and installs eSpeak NG. `install_ollama_pi.sh` does enable `ollama.service`, because a model cannot be pulled without it; nothing else is enabled. Run `scripts/verify_hardware.sh`, and explicitly install/enable `manny-core` and `manny-kiosk` only after validation.

The default Pi inference budget is one conversational model, a 148 MB multilingual Whisper model, a 4,096-token runtime context, and one loaded model at a time. No systemd memory ceiling is set: the conversational model's resident size is unmeasured, and a guessed ceiling either does nothing or OOM-kills the model long after deployment. These are starting values, not performance claims; simultaneous STT, LLM, TTS, camera, latency, thermals, memory, and power must be measured on the actual Pi 5 enclosure.

`gemma4:e2b` is the conversational default and also handles image input, which is why no separate vision model or second server exists any more (ADR-020). The local model never calls a tool: it returns a schema-constrained intent and wording, and the policy broker performs every MCP request, so its job is classification and phrasing rather than tool use.

The Pi 5 has no usable GPU offload, so generation is bound by memory bandwidth. An E2B-class model carries around 2B active parameters out of a larger stored set, and whether it fits 8 GB depends on the runtime offloading its per-layer embeddings. Read `ollama ps` on the device before trusting any memory figure; nothing here sets a ceiling for that reason. A partially offloaded model also faults to disk mid-generation, which makes NVMe part of the inference path rather than a build-time convenience.

`MANNY_OLLAMA_MODEL` selects the tag `install_ollama_pi.sh` pulls, defaulting to `gemma4:e2b`, and `MANNY_LLM_MODEL` in `/opt/manny/.env` must name the same tag so the core asks for something that is present. Changing models is now one variable and a pull rather than a source build.

The runtime binary is checksum-verified: `MANNY_OLLAMA_URL` and `MANNY_OLLAMA_SHA256` are required and the installer refuses without them, because a service binary is arbitrary code execution rather than data. Model pulls are **not** verified — Ollama's registry offers no equivalent to a pinned SHA, and giving that guarantee up is what adopting Ollama costs (ADR-020).

Before relying on a tag, confirm what it is: `ollama show <tag>` reports its parameters, quantisation and whether it advertises vision. A model whose weights include a vision encoder is not the same as a runtime that exposes one, and image support has historically lagged the text path.

Physical selection remains for display/touch, camera FOV, microphone, acoustics, speaker/amplifier, LED controller, controls, GPIO, privacy wiring, power, thermal behavior, and enclosure.

## Bring-up verification

`scripts/verify_hardware.sh` separates two questions that first boot tends to
conflate: is a prerequisite installed, and does the hardware actually work.

Presence checks report `MISSING` when a binary, model, or device node is absent.
Function checks drive the device and report `FAILED` with the likely cause:

- records two seconds from `MANNY_AUDIO_DEVICE` and measures the signal level, so
  a muted mixer or the wrong card is reported as silence rather than success
- feeds that recording to whisper.cpp, which validates capture and speech
  recognition together
- synthesizes with eSpeak NG and plays it through the speaker
- captures a camera frame and confirms `picamera2` imports, since the runtime
  adapter needs the module rather than the command
- reports whether OpenCV is available, because presence detection stays at zero
  without a detector
- checks the LED and brightness sysfs paths are writable *by the service user*
- asks the local model for a completion, not just a health check
- loads and validates the `raspberrypi` settings profile

```bash
./scripts/verify_hardware.sh              # presence and function
./scripts/verify_hardware.sh --quick      # presence only, no sound
./scripts/verify_hardware.sh --no-audio   # skip anything that emits sound
./scripts/verify_hardware.sh --loopback   # also confirm the mic hears the speaker
```

Run it as the `manny` service user. Running as root can pass sysfs writability
checks that then fail in the service.

`--loopback` plays a phrase while recording and asserts the microphone picked it
up. It is the closest single check to a working voice turn, and it will fail on
a device whose speaker and microphone are correctly isolated — treat a failure
there as information about placement, not necessarily a fault.
