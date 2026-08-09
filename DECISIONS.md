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

Status: Accepted

Decision: Use Gemma 3 1B Instruction-Tuned Q4_K_M as the initial Raspberry Pi 5 8 GB conversational model through a loopback-only llama.cpp server. Constrain and validate its routing output, keep only short volatile non-financial context, never expose credentials, and preserve deterministic policy and fallback behavior. Treat a move to a larger model as a benchmark-driven hardware decision.

## ADR-016 — Multilingual local interaction

Status: Accepted

Decision: Carry normalized BCP-47 language metadata through STT, agent, API, browser, and TTS boundaries. Use multilingual whisper.cpp base inference for automatic local recognition and eSpeak NG for broad offline speech output. Gemma must reply in the user's language; finance wording may contain only validated placeholders, with real MCP values inserted by deterministic host code after policy and schema checks. Built-in templates cover major languages and English remains the safe final fallback.

## ADR-016 — Multimodal conversational model on the device

Status: Accepted

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
does not load a projector. The multimodal model is retained for its stronger
instruction-following and multilingual quality; scene description is a
configuration change away once hardware is chosen.

While the camera is off, presence is always absent. MULTIPLE_PEOPLE cannot occur,
so the automatic masking of financial values when others are nearby does not
engage and the passcode is the only gate on private views.
