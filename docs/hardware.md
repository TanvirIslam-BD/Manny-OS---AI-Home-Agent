# Raspberry Pi Hardware Integration

Manny targets Raspberry Pi 5 8 GB **with NVMe** on 64-bit Raspberry Pi OS. The NVMe drive is a requirement rather than an upgrade: the conversational model is larger than the RAM left for it and depends on being paged from fast storage (ADR-021). No final peripheral identifiers or GPIO mappings are encoded in source.

Device configuration includes `MANNY_AUDIO_DEVICE`, optional LED/display sysfs paths, camera privacy state, and the selected local STT/TTS/LLM backends.

Run `scripts/bootstrap_pi.sh` only after review. It verifies ARM64 Raspberry Pi hardware, asks for confirmation, installs prerequisites, and creates the service user. Run `scripts/install_app_pi.sh` from the reviewed source tree to copy Manny into `/opt/manny`, create its Python environment, and build the UI. Install `configs/raspberrypi.env.example` as `/opt/manny/.env` with mode `0600`, then replace its placeholder timezone and MCP endpoint. Next run `/opt/manny/scripts/install_ollama_pi.sh` and `scripts/install_multilingual_voice_pi.sh`; the first installs a checksum-verified Ollama runtime, applies Manny's hardening drop-in, and pulls `gemma3n:e2b`, while the second builds pinned whisper.cpp source, downloads the checksum-verified multilingual Whisper base model, and installs eSpeak NG. `install_ollama_pi.sh` does enable `ollama.service`, because a model cannot be pulled without it; nothing else is enabled. Run `scripts/verify_hardware.sh`, and explicitly install/enable `manny-core` and `manny-kiosk` only after validation.

The default Pi inference budget is one conversational model, a 148 MB multilingual Whisper model, a 4,096-token runtime context, and one loaded model at a time. No systemd memory ceiling is set: the conversational model's resident size is unmeasured, and a guessed ceiling either does nothing or OOM-kills the model long after deployment. These are starting values, not performance claims; simultaneous STT, LLM, TTS, camera, latency, thermals, memory, and power must be measured on the actual Pi 5 enclosure.

`gemma3n:e2b` is the conversational default and also handles image input, which is why no separate vision model or second server exists any more (ADR-020). The local model never calls a tool: it returns a schema-constrained intent and wording, and the policy broker performs every MCP request, so its job is classification and phrasing rather than tool use.

The Pi 5 has no usable GPU offload, so generation is bound by memory bandwidth. An E2B-class model carries around 2B active parameters out of a larger stored set, and whether it fits 8 GB depends on the runtime offloading its per-layer embeddings. Read `ollama ps` on the device before trusting any memory figure; nothing here sets a ceiling for that reason. A partially offloaded model also faults to disk mid-generation, which makes NVMe part of the inference path rather than a build-time convenience.

`MANNY_OLLAMA_MODEL` selects the tag `install_ollama_pi.sh` pulls, defaulting to `gemma3n:e2b`, and `MANNY_LLM_MODEL` in `/opt/manny/.env` must name the same tag so the core asks for something that is present. Changing models is now one variable and a pull rather than a source build.

The runtime binary is checksum-verified: `MANNY_OLLAMA_URL` and `MANNY_OLLAMA_SHA256` are required and the installer refuses without them, because a service binary is arbitrary code execution rather than data. Model pulls are **not** verified — Ollama's registry offers no equivalent to a pinned SHA, and giving that guarantee up is what adopting Ollama costs (ADR-020).

Before relying on a tag, confirm what it is: `ollama show <tag>` reports its parameters, quantisation and whether it advertises vision. A model whose weights include a vision encoder is not the same as a runtime that exposes one, and image support has historically lagged the text path.

## LiteRT-LM: measured and rejected

LiteRT-LM was evaluated as a replacement for Ollama and rejected on one measurement.
Everything else about it was better, so the reason is worth recording.

What worked, tested against `litert-lm serve` 0.15.0 with Gemma 4 E2B and this
project's real system instruction:

- Schema-constrained output works. The server accepts the exact `response_format`
  payload the adapter sends and enforces it with llguidance. Replies parsed as valid
  JSON with exactly the schema's keys and an intent inside the enum.
- Routing was correct on all five intents tried, and every finance intent left
  `reply` empty and put only approved placeholders in `reply_template`, with no
  invented numbers. That is the behaviour the finance boundary depends on.
- Streaming works and its delta shape is what `_stream_delta` already parses.
- The model is 2,468 MB on disk against 6.67 GB for the Ollama GGUF, and resident
  memory during inference measured 2,871 MB on x86-64.

What ruled it out: **`litert-lm serve` does not cache the prompt prefix across
requests.** Three identical requests took 10.9 s, 10.8 s and 10.7 s, a spread of
0.2 s. Its handler builds a fresh conversation per HTTP request, so the system
instruction is re-prefilled every turn. Isolating it, 731 extra prompt tokens cost
8.2 s, about 89 tok/s prefill.

That defeats the design in `_complete`, which places the invariant instruction first
precisely so the runtime holds it in the prompt cache. llama.cpp and Ollama do; this
server does not. On a Pi 5 at Google's 133 tok/s the penalty is roughly 5.7 seconds
added to every single turn, before any generation.

The library is not the problem, the server is: the Python API holds a `Conversation`
object whose cache would persist. Using it would mean writing our own local service
rather than pointing a base URL somewhere else, and holding conversation state
outside the history handling that already exists. That is a much larger change than
the swap this evaluation was testing, and it is not currently justified.

One practical note for any future attempt: `litert-lm import --from-huggingface-repo`
hangs indefinitely at zero bytes without a TTY, so an unattended installer must fetch
the model with `curl` and then `import` from a local path.

## Measured Raspberry Pi 5 performance

Google publishes LiteRT-LM benchmarks for Gemma 4 on a Raspberry Pi 5, CPU backend.
These are the first vendor numbers for this class of model on this board, and they
replace several estimates that were previously recorded here:

| | Gemma-4-E2B | Gemma-4-E4B |
| --- | --- | --- |
| Model size (LiteRT-LM format) | 2.58 GB | 3.65 GB |
| Decode | 8 tok/s | 3 tok/s |
| Prefill | 133 tok/s | 51 tok/s |
| Time to first token | 7.8 s | 20.5 s |
| Peak CPU memory | 1,546 MB | 3,069 MB |

Source: https://developers.google.com/edge/litert-lm/models/gemma-4

Three things follow.

Memory is not the constraint it appeared to be, but the artefact matters: the same
model is 2.58 GB as a LiteRT-LM build and 6.67 GB as an Ollama GGUF. Peak memory of
1.5 GB fits an 8 GB board with room; the 6.67 GB figure recorded below applies only
to the GGUF served by Ollama.

Prefill makes the system instruction a latency cost, not a free constant. It measures
758 tokens, which at 133 tok/s is roughly six seconds — close to the 7.8 s
time-to-first-token above. That is why `_complete` places the invariant instruction
first: the runtime keeps it in the prompt cache, and only a cache miss pays for it.
Shortening it is now a measurable win rather than tidiness.

E4B is not a candidate. Twenty seconds to first token is not a conversation.

Decode at 8 tok/s means a fifty-token reply takes about six seconds to generate. The
sentence-level streaming in `agent/streaming.py` is what makes that tolerable: the
first sentence is spoken while the rest is still being decoded, so the wait is a
sentence rather than a paragraph.

Multi-Token Prediction is available and should be left off here. Google recommends it
for rewriting, summarising and coding, and notes it can slow down freeform generative
prompting — which is what conversation is.

## Fitting the conversational model in 8 GB

An E2B-class model stores far more than it activates: roughly 2B active parameters
out of a larger set held as per-layer embeddings. Sizes read from the registry
manifest rather than estimated:

| Tag | Model layer | Against ~6.3 GB available |
| --- | --- | --- |
| `gemma3n:e2b` | 5.24 GB | fits, can be fully resident, **the default** |
| `gemma4:e2b` | 6.67 GB | exceeds it; only runs partially resident |
| `gemma4:e4b` | 8.95 GB | no |

No smaller quantisation of either is published, so there is no cheaper variant of
this choice.

The default was chosen to fit rather than to be best. Even at 5.24 GB, Ollama mmaps
its weights, so what has to be resident is the hot working set rather than the whole
file, which is why NVMe is required here and a microSD card is not sufficient. Cold
pages are faulted during generation, and read latency shows up as pauses
mid-sentence.

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
- `OLLAMA_CONTEXT_LENGTH=3072` — Manny's prompt reaches about 1,700 tokens: a system
  instruction measured at 758 tokens by a real tokeniser, four turns of history, four
  recalled notes, the question, and a 320-token reply. A larger context only enlarges
  the KV cache; a smaller one risks truncating the instruction that carries the
  finance rules.
- `OLLAMA_FLASH_ATTENTION=1` with `OLLAMA_KV_CACHE_TYPE=q8_0` — roughly halves the
  KV cache.
- `llm_context_turns: 4` on device profiles — fewer prompt tokens, and retrieval
  covers what falls out of the window rather than the window being the whole memory.
- `OLLAMA_MAX_LOADED_MODELS=1` — vision and conversation share one model, so nothing
  should ever want a second.

`install_ollama_pi.sh` already configures the memory side of this, because on this
board it is part of the design rather than a remedy:

- **zram** at 25% with zstd, so Chromium's anonymous pages can be evicted into
  compressed RAM instead of costing the page cache that holds the model. Sized
  conservatively: zram's own compressed pages occupy RAM, so a larger device is not
  free, and page cache is what this device is short of.
- **`vm.swappiness=100`**, biasing the kernel toward evicting anonymous pages rather
  than dropping mmapped model pages — the first costs a compressed copy, the second
  costs a disk fault mid-generation.
- **SD-card swap disabled.** zram replaces `dphys-swapfile` rather than joining it. A
  fault to the card during generation is indistinguishable from a hang.
- **mmap left enabled.** Never set `OLLAMA_NO_MMAP`: it would require the whole 6.67 GB
  resident, which this board cannot do.

If `ollama ps` still reports more than the board can hold, the levers in order are:

1. **Drop the kiosk.** `systemctl disable --now manny-kiosk` frees roughly 1.5 GB, and
   the UI still works from another machine's browser on the same network.
2. **A 16 GB board.** It fits either model outright, at the same speed; bandwidth is
   unchanged.

Running `gemma4:e2b` instead is one variable and a pull, once `ollama ps` has shown
there is room for it:

```bash
sudo MANNY_OLLAMA_MODEL=gemma4:e2b ./scripts/install_ollama_pi.sh
# then set MANNY_LLM_MODEL=gemma4:e2b in /opt/manny/.env
```

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
