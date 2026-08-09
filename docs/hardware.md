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

## Fitting the conversational model in 8 GB

An E2B-class model stores far more than it activates: roughly 2B active parameters
out of a larger set held as per-layer embeddings. `gemma4:e2b`'s model layer is
**6.67 GB** — read from the registry manifest, not estimated — against `gemma4:e4b` at
8.95 GB and `gemma3n:e2b` at 5.24 GB. No smaller quantisation of `gemma4` is
published.

That file does not fit an 8 GB board fully resident: about 1.5 GB is committed before
the model loads (below), leaving roughly 6.3 GB of about 7.8 GB usable. It works
anyway only because Ollama mmaps its weights, so what has to be resident is the hot
working set rather than the file. For a ~2B-active model that is far smaller — but the
cold pages have to come from somewhere fast, which is why NVMe is required here and a
microSD card is not sufficient.

Whether the working set really is small enough is a property of the runtime, not the
model, so it has to be measured:

```bash
ollama ps          # resident size while the model is loaded
ollama show <tag>  # parameters, quantisation, and whether vision is advertised
```

Read that number before trusting any budget below. Nothing in this repository sets a
memory ceiling, because a guessed one either does nothing or kills the model weeks
after deployment.

The rest of the board, approximately:

| Consumer | Resident |
| --- | --- |
| Raspberry Pi OS Desktop session | ~0.4 GB |
| Chromium kiosk with the UI loaded | ~0.8–1.1 GB |
| Manny core (FastAPI, SQLite) | ~0.2 GB |
| whisper.cpp, only while transcribing | ~0.4 GB |

So roughly 1.5 GB is committed before the model loads, against about 7.8 GB usable
after GPU/CMA reservation — about 6.3 GB for the model. Comfortable if `ollama ps`
reports 2–3 GB resident; not if it reports anything approaching the 6.67 GB on disk.

What the configuration already does to help:

- `OLLAMA_NUM_PARALLEL=1` — each parallel slot carries its own KV cache, and a
  half-duplex device runs one turn at a time, so more than one slot buys nothing.
- `OLLAMA_CONTEXT_LENGTH=3072` — Manny's prompt reaches about 1,950 tokens: a
  ~940-token system instruction (the multilingual routing examples tokenise far worse
  than their character count suggests), four turns of history, four recalled notes,
  the question, and a 320-token reply. A larger context only enlarges the KV cache;
  a smaller one risks truncating the instruction that carries the finance rules.
- `OLLAMA_FLASH_ATTENTION=1` with `OLLAMA_KV_CACHE_TYPE=q8_0` — roughly halves the
  KV cache.
- `llm_context_turns: 4` on device profiles — fewer prompt tokens, and retrieval
  covers what falls out of the window rather than the window being the whole memory.
- `OLLAMA_MAX_LOADED_MODELS=1` — vision and conversation share one model, so nothing
  should ever want a second.

If `ollama ps` still reports too much, in order of preference:

1. **zram.** Compressed swap in RAM gives Chromium's idle pages somewhere cheap to
   go. Never let model weights reach SD-card swap; random reads there are 10–40 MB/s
   and generation stops being conversational.
   ```bash
   sudo apt-get install -y zram-tools
   sudo systemctl restart zramswap
   ```
2. **Drop the kiosk.** `systemctl disable --now manny-kiosk` frees roughly 1.5 GB and
   the UI still works from another machine's browser on the same network.
3. **More memory, or less model.** A 16 GB board keeps the same bandwidth — it fits,
   it does not speed up — or set `MANNY_OLLAMA_MODEL` to a smaller tag, which is now
   one variable and a pull.

Storage is part of this. A partially offloaded model faults to disk during
generation, so NVMe belongs in the inference path: roughly 400+ MB/s random read
against 10–40 MB/s on a microSD card. This reverses the earlier reasoning that
storage could not matter to a memory-bandwidth-bound decode — it could not, for a
model held entirely in RAM.

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
