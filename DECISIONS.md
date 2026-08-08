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

Decision: Store reminders and minimal timestamped finance cache in SQLite. Development OAuth data uses an ignored restrictive file; production requires an OS keyring.

## ADR-014 — Optional local media runtimes

Status: Accepted

Decision: Keep Moonshine, Kokoro, Picamera2, and ALSA behind protocols and load them only in configured device modes so desktop development and CI stay deterministic.
