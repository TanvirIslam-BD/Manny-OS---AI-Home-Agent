# Architecture Decisions

## ADR-001 — Raspberry Pi OS base

Status: Accepted

Decision: Manny OS is an application stack deployed on Raspberry Pi OS 64-bit, not a custom Linux distribution.

## ADR-002 — FastAPI and React/Vite

Status: Accepted

Decision: Use FastAPI for the localhost service and React, TypeScript, and Vite for the kiosk UI and development simulator.

## ADR-003 — MCP for Money Copilot

Status: Accepted

Decision: Money Copilot communication will use the official MCP SDK. Production remote transport will use Streamable HTTP over HTTPS.

## ADR-004 — Financial truth boundary

Status: Accepted

Decision: Current financial values come only from validated MCP results or timestamped cache. Simulator fixtures are visibly labelled demo data.

## ADR-005 — Local camera processing

Status: Accepted

Decision: Presence processing is local by default. Frames remain in memory and are discarded after inference unless the user explicitly requests a capture flow.

## ADR-006 — Stationary V1 device

Status: Accepted

Decision: Manny V1 has no motors, wheels, navigation, or room mapping.

## ADR-007 — Mockable hardware

Status: Accepted

Decision: Camera, audio, LED, and display functionality is accessed through typed adapters with mock implementations for normal development and CI.

## ADR-008 — Deterministic authorization

Status: Accepted

Decision: Tool authorization and confirmation policy will be deterministic application code, not an LLM decision.

## ADR-009 — Local API exposure

Status: Accepted

Decision: The API binds to `127.0.0.1` by default. Remote access requires an explicit later security decision.

## ADR-010 — No high-risk finance actions

Status: Accepted

Decision: V1 will not expose payment, transfer, trading, credit, or bank-credential actions.

## ADR-011 — Official MCP SDK v2 and OAuth 2.1

Status: Accepted

Decision: Use the official MCP Python SDK v2 for the 2026-07-28 protocol over Streamable HTTP. Protected remote servers use OAuth discovery, PKCE, dynamic registration, and explicit browser authorization. Discovered tools remain non-callable until their names are placed in the deterministic allowlist.

## ADR-012 — Semantic finance normalization

Status: Accepted

Decision: Normalize provider-specific structured results into Manny's typed semantic models inside the host broker. Unsupported semantics are reported unavailable rather than inferred from unrelated tools.

## ADR-013 — Local persistence and credentials

Status: Accepted

Decision: Store reminders and minimal timestamped finance cache in SQLite. OAuth data uses an ignored mode-0600 file; the `production` environment additionally requires an OS keyring and refuses to start without one.

The Raspberry Pi profile is deliberately not held to the keyring requirement. A headless appliance has to restore its connection after a power cut with nobody present, so a vault would need to unlock itself, which puts the unlocking secret on the same SD card as the tokens. Pi 5 has no TPM to bind it to, so an auto-unlocked vault is a mode-0600 file plus a daemon that can strand the device — more failure surface for no gain against the threat that matters, which is someone taking the card.

Consequence, recorded rather than implied: on the device, physical possession is possession of the Money Copilot session. Loss is handled by revoking server-side, not by on-device protection. Closing this properly needs hardware — a TPM or secure element — and is a hardware decision, not a software one.

## ADR-014 — Optional local media runtimes

Status: Accepted

Decision: Keep Moonshine, Kokoro, Picamera2, and ALSA behind protocols and load them only in configured device modes so desktop development and CI stay deterministic.

## ADR-015 — Local conversational model

Status: Superseded by ADR-020 (runtime and model); its constraints on the model's role still hold

Decision: Use Gemma 3 1B Instruction-Tuned Q4_K_M as the initial Raspberry Pi 5 8 GB conversational model through a loopback-only llama.cpp server. Constrain and validate its routing output, keep only short volatile non-financial context, never expose credentials, and preserve deterministic policy and fallback behavior. Treat a move to a larger model as a benchmark-driven hardware decision.

## ADR-016 — Multilingual local interaction

Status: Accepted

Decision: Carry normalized BCP-47 language metadata through STT, agent, API, browser, and TTS boundaries. Use multilingual whisper.cpp base inference for automatic local recognition and eSpeak NG for broad offline speech output. Gemma must reply in the user's language; finance wording may contain only validated placeholders, with real MCP values inserted by deterministic host code after policy and schema checks. Built-in templates cover major languages and English remains the safe final fallback.

## ADR-017 — Multimodal conversational model on the device

Status: Superseded by ADR-020. Scene description moved to the same multimodal model as conversation, so the separate vision model and its second server are both gone

Decision: Raspberry Pi and production profiles use Gemma 3 4B IT Q4_K_M as a
single multimodal model serving both conversation and camera scene description,
replacing the 1B text-only default of ADR-015 on those profiles. Development
stays on 1B, which is faster and sufficient for intent routing.

Rationale: the 1B model cannot accept an image, so "what am I holding" had no
possible local answer. Answering it in the cloud was rejected: camera frames and
conversation must not leave the device.

Consequences: a larger memory and latency budget on 8 GB hardware, shared with
speech recognition, synthesis, and the browser. The systemd ceiling moves from
5 GB to 6 GB. These are starting values, not measurements — latency and thermals
under load remain an open hardware gate.

Amendment: the camera is deferred until a sensor is selected, so device profiles
ship with camera_enabled false and vision_language_backend none, and the service
does not load a projector. With no image to accept, the reason for 4B on the
conversational path went with it, and ADR-019 returns that path to 1B for latency.
4B stays the choice for scene description once a sensor is chosen, on its own
llama-server instance rather than by switching the conversational model back.

While the camera is off, presence is always absent. MULTIPLE_PEOPLE cannot occur,
so the automatic masking of financial values when others are nearby does not
engage and the passcode is the only gate on private views.

## ADR-018 — Fully local inference, with no cloud fallback

Status: Accepted

Decision: All inference stays on the device. Conversation, intent routing, speech
recognition, and speech synthesis run locally, and there is no cloud model in any
path — including as a fallback when the local model fails validation.

Rationale: cloud inference would not fix the latency that motivated considering it.
Financial questions never reach the language model at all — `DeterministicIntentModel`
classifies them first and the policy broker performs the call — so a remote model
could only accelerate open conversation, and a network round trip is frequently no
faster than Gemma 3 1B on this hardware. Against that it would trade the privacy
posture that is the product's premise, and add a dependency that makes the device
useless when the connection is down. The remaining latency is structural (fixed
capture window, nothing streaming) and is addressable locally.

Consequences: conversational quality is capped by what a 1B model can do on four
Cortex-A76 cores. When the local model returns something that fails schema
validation twice, the deterministic fallback line is the final answer — there is no
escape hatch, by choice. Any future quality increase is a local-model or hardware
decision, not a hosting one. This does not constrain MCP: tool data still comes from
the configured remote server, which is a data boundary, not an inference one.

## ADR-019 — Gemma 3 1B for conversation on the device

Status: Superseded by ADR-020

Decision: Raspberry Pi and production profiles use Gemma 3 1B IT for conversation,
restoring the ADR-015 default on those profiles and superseding ADR-017's choice of
4B for the conversational path. 4B remains the model for camera scene description,
where the capability gap is real rather than a quality preference.

Rationale: Pi 5 has no usable GPU offload for llama.cpp, so generation is bound by
memory bandwidth and 4B costs roughly three times as long per token. The device's
language model classifies intent and drafts wording; it never calls a tool. Latency
is the binding constraint on a conversational appliance, and quality beyond what 1B
provides does not buy a better answer for work the broker performs anyway.

Consequences: routing accuracy at 1B is the risk, not speed, and it has not been
measured against a labelled set of real utterances. Qwen3 1.7B is the fallback if
routing proves too weak, with Bengali and Hindi template quality to re-verify before
adopting it. Enabling scene description means installing 4B with its projector on a
second llama-server, not switching the conversational model back.

## ADR-020 — Ollama as the local runtime, with a multimodal E2B model

Status: Accepted

Decision: Ollama replaces llama.cpp as the only local inference runtime, and the
conversational model becomes `gemma4:e2b` — an E2B-class model of roughly 2B active
parameters drawn from a larger stored model, natively capable of text and image.
Supersedes ADR-015's choice of runtime and ADR-019's choice of model. Speech
recognition stays on whisper.cpp.

Rationale: the adapter was always an OpenAI-compatible chat client, so the runtime
was never load-bearing in the code — the switch is a base URL and a port. What it
buys is a model that handles image input, which retires the separate 4B vision model
ADR-017 introduced and the second server it needed. It also makes changing models a
configuration change instead of a source build, which matters while the right model
for this device is still unknown.

Consequences, stated because several are losses:

Model weights are no longer checksum-verified. `install_gemma_pi.sh` refused to
download anything without a SHA the operator had checked; Ollama's registry offers no
equivalent, so that guarantee is gone. The Ollama binary is still verified, because
it runs as a service and that is arbitrary code execution rather than data.

Vision and conversation now share an endpoint and a model. The separate port and
separate weights were llama.cpp constraints — one server, one model — not
requirements.

Predictability is traded for flexibility. A model manager can unload between turns
where a pinned llama-server never did, so `OLLAMA_KEEP_ALIVE=-1` is set to stop a
multi-second reload landing mid-conversation.

The tag was confirmed against the Ollama registry manifest rather than assumed: it
exists, and its model layer is 6.67 GB. `gemma4:e4b` is 8.95 GB and `gemma3n:e2b` —
the previous generation of the same class — is 5.24 GB. No smaller quantisation of
`gemma4` is published.

6.67 GB does not fit an 8 GB board as a fully resident model. Roughly 1.5 GB is
already committed to the desktop session, the Chromium kiosk, the core and whisper,
leaving about 6.3 GB. Two things make it viable anyway: Ollama mmaps its weights, so
only the hot working set needs to be resident and for a ~2B-active model that is far
smaller than the file — provided cold pages are served from NVMe rather than a
microSD card — and the kiosk can be dropped for about 1.5 GB. A 16 GB board fits it
outright, at the same speed, since bandwidth is unchanged.

What remains unmeasured is the resident size in practice. No memory ceiling is set
anywhere until `ollama ps` has been read on the device, because a guessed ceiling
either does nothing or kills the model weeks later.

Storage moved into the inference path. A partially offloaded model faults to disk
during generation, so NVMe is required rather than optional — which reverses the
earlier reasoning that storage speed could not affect a bandwidth-bound decode.

Reverting means restoring `install_gemma_pi.sh`, `manny-llm.service` and the
`model.env` mechanism from history, and pointing `llm_base_url` back at port 8080.

## ADR-021 — 8 GB board with NVMe, and mmap as the mechanism that makes it fit

Status: Accepted

Decision: Manny targets a Raspberry Pi 5 8 GB with an NVMe drive, running
`gemma4:e2b` whose model layer is 6.67 GB. NVMe is a requirement, not an upgrade.

Rationale: the model file is larger than the memory left for it — roughly 6.3 GB of
7.8 GB usable, once the desktop session, Chromium kiosk, core and whisper have taken
their share. It loads anyway because Ollama mmaps its weights, so what must be
resident is the hot working set rather than the whole file, and for a model with
around 2B active parameters that is far smaller. A 16 GB board would fit it outright
at identical speed, since memory bandwidth is unchanged; 8 GB with NVMe was chosen
instead, which makes the offloading mechanism load-bearing rather than incidental.

Consequences:

Storage is in the inference path. Cold pages are faulted during generation, so read
latency shows up as pauses mid-sentence. NVMe delivers 400+ MB/s random read; a
microSD card delivers 10–40 MB/s, which is slow enough that a fault reads as a hang.
The installer warns when the model store is not on NVMe and bring-up fails the check.

mmap must stay enabled. `OLLAMA_NO_MMAP` would require the whole file resident, which
this board cannot do, so the drop-in carries a comment against setting it. Someone
disabling it to fix an unrelated symptom would produce a device that cannot load its
model at all.

Memory headroom is part of the design. zram provides compressed swap in RAM so
Chromium's anonymous pages can be evicted without costing the page cache that holds
the model, and `vm.swappiness=100` biases the kernel toward doing that rather than
dropping model pages. SD-card swap is disabled outright, since a fault there during
generation is indistinguishable from a hang.

There is little margin. If measurement on the device shows the working set is larger
than hoped, the levers in order are dropping the Chromium kiosk for about 1.5 GB,
switching to `gemma3n:e2b` at 5.24 GB — one environment variable — or moving to a
16 GB board. `ollama ps` is what decides.
