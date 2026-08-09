# Manny OS

Manny OS is the software stack for **Manny Copilot**, a stationary, privacy-conscious AI
home and desk companion powered by Money Copilot AI. It combines a local conversational
model, multilingual voice, presence-aware hardware adapters, and a policy-controlled Money
Copilot MCP connection. This repository includes the desktop simulator and the deployable
Raspberry Pi 5 runtime.

This README is the primary starting point for people and coding agents. It explains the
system boundaries, repository map, runtime flows, development workflow, deployment process,
and current limitations. Before changing architecture or behavior, also read
[MANNY_OS_REQUIREMENTS.md](MANNY_OS_REQUIREMENTS.md), [DECISIONS.md](DECISIONS.md),
[ASSUMPTIONS.md](ASSUMPTIONS.md), and [ROADMAP.md](ROADMAP.md).

## System invariants

These rules are architectural constraints, not optional conventions:

- Financial values come only from validated MCP responses or clearly labelled local cache.
  Never let an LLM invent balances, budgets, transactions, dates, or amounts.
- The local LLM never receives MCP credentials, raw authorization tokens, or permission to
  execute tools. It may classify intent and draft general conversation only.
- All inference runs on the device. There is no cloud model in any path, including as a
  fallback when the local model fails validation (ADR-018). MCP is a data boundary, not an
  inference one: tool results come from the configured remote server, prompts never do.
- All MCP calls pass through the deterministic policy broker and explicit tool allowlist.
- Manny does not expose payment, transfer, trading, or other irreversible financial actions.
- Local services bind to loopback by default. Do not expose the API or the Ollama daemon to a
  network without adding authentication and updating the threat model.
- Camera processing is presence-oriented. Face recognition and identity storage are disabled.
- Secrets, tokens, models, local databases, logs, and `.env` files must remain outside Git.
- Preserve mock adapters and hardware-independent tests whenever adding a real device adapter.
- A degraded dependency must produce an honest unavailable, cached, or offline state—not
  fabricated demo data presented as live data.

## Current capabilities

- Responsive Manny device simulator with idle, present, listening, thinking, speaking,
  dashboard, alert, offline, microphone-muted, camera-off, and error expressions
- FastAPI core with REST endpoints, WebSocket events, health checks, metrics, and one
  authoritative application state machine
- Official MCP Python SDK v2 client using Streamable HTTP and OAuth 2.1 authorization
- Validated live budget/category dashboard with disclosed cache age during outages
- Local `gemma4:e2b` companion, text and image, through a loopback-only Ollama daemon
- Multilingual typed and spoken interaction with automatic language detection
- Local Whisper speech-to-text and eSpeak NG text-to-speech on Raspberry Pi
- Browser microphone, speech synthesis, and camera presence simulation on desktop
- Reminders, proactive alerts, policy enforcement, structured logging, and privacy lock
- Mock and real interfaces for camera, microphone, speaker, LED, display, and presence sensors
- Raspberry Pi installers, systemd units, kiosk configuration, and release tooling

## Architecture at a glance

```text
Browser simulator / Pi hardware
        │
        ▼
FastAPI routes + WebSocket events
        │
        ▼
Authoritative state machine ───────► UI expression / LEDs / display / speaker
        │
        ├──► Voice: Whisper STT ─► language tag ─► agent ─► eSpeak/browser TTS
        │
        ├──► General conversation ─► local model through Ollama
        │
        └──► Finance intent
                │
                ▼
             Policy broker ─► allowlisted MCP tool ─► response validation
                                                        │
                                                        ▼
                                               safe formatter + cache
```

The dependency graph is assembled in `apps/core/manny/lifecycle.py`. API handlers should
delegate to these services instead of constructing their own clients or state. The main
request path is:

1. Accept text or transcribed speech and attach a detected language.
2. Classify cancellation, device controls, reminder requests, finance intent, or general chat.
3. Route general chat to the local model; route finance intent through policy and MCP.
4. Validate external data against typed contracts before formatting it for the user.
5. Update the state machine and publish an event to the UI/device adapters.
6. Speak the same safe response in the selected language when voice output is enabled.

## Repository map

```text
Manny-OS---AI-Home-Agent/
├── apps/
│   ├── core/manny/             Python runtime package
│   │   ├── agent/              Intent routing, Ollama client, agent models
│   │   ├── api/                REST routes and WebSocket event hub
│   │   ├── hardware/           Hardware protocols plus mock and real adapters
│   │   ├── mcp/                MCP clients, OAuth/token storage, contracts, validation
│   │   ├── notifications/      Alerts and notification delivery
│   │   ├── observability/      Structured logging, metrics, operational signals
│   │   ├── policy/             Tool allowlist and action safety broker
│   │   ├── reminders/          Reminder parsing, scheduling, and persistence
│   │   ├── security/           Rate limits and security helpers
│   │   ├── state/              Authoritative device/application state machine
│   │   ├── storage/            Local cache and persistent runtime data
│   │   ├── vision/             Presence detection and camera privacy behavior
│   │   ├── voice/              STT, TTS, voice orchestration, locale handling
│   │   ├── config.py           Typed settings and profile loading
│   │   ├── i18n.py             Language detection, normalization, safe translations
│   │   ├── lifecycle.py        Startup/shutdown and dependency composition root
│   │   └── main.py             FastAPI application entry point
│   └── ui/                     React, TypeScript, and Vite device simulator
├── configs/                    Development, production, and Raspberry Pi profiles
├── docs/                       Architecture, hardware, MCP, privacy, security, operations
├── mcp_servers/manny_local/    Local mock MCP server for deterministic development
├── scripts/                    Setup, validation, release, Pi, Ollama, and voice tooling
├── systemd/                    Core API and kiosk service definitions
├── tests/
│   ├── contract/               MCP and boundary contract tests
│   ├── hardware/               Adapter behavior tests
│   ├── integration/            Cross-service runtime tests
│   ├── unit/                   Isolated Python tests
│   └── e2e/                    End-to-end test scaffolding
├── .github/workflows/          Validation, security, and release workflows
├── MANNY_OS_REQUIREMENTS.md    Product and system requirements
├── DECISIONS.md                Accepted architectural decisions
├── ASSUMPTIONS.md              Explicit assumptions and validation gates
├── ROADMAP.md                  Remaining work and external blockers
├── SECURITY.md                 Security model and reporting process
├── CONTRIBUTING.md             Contribution workflow and standards
├── Makefile                    Common developer and deployment commands
└── pyproject.toml              Python dependencies and tool configuration
```

### Where to make a change

| Goal | Start here | Also inspect |
| --- | --- | --- |
| Change conversation or intent routing | `apps/core/manny/agent/runtime.py` | `agent/models.py`, `policy/`, agent tests |
| Change local model behavior | `apps/core/manny/agent/ollama.py` | profile YAML, LLM system prompt tests |
| Add or change an MCP tool | `apps/core/manny/mcp/` | `policy/`, `docs/mcp-contract.md`, contract tests |
| Add a REST or WebSocket feature | `apps/core/manny/api/` | `lifecycle.py`, state and integration tests |
| Change a device expression/state | `apps/core/manny/state/` | `apps/ui/src/`, hardware adapters |
| Add a language or localized finance phrase | `apps/core/manny/i18n.py` | voice orchestration and multilingual tests |
| Change speech input/output | `apps/core/manny/voice/` | browser voice code, Pi voice installer |
| Change camera/presence behavior | `apps/core/manny/vision/` | hardware adapters and privacy tests |
| Add physical hardware | `apps/core/manny/hardware/` | `docs/hardware.md`, config profiles |
| Change simulator appearance | `apps/ui/src/` | UI tests and shared API types |
| Change Raspberry Pi installation | `scripts/install_*_pi.sh` | `systemd/`, `configs/raspberrypi.yaml` |

## Configuration

Settings are typed in `apps/core/manny/config.py`. Effective precedence is:

```text
MANNY_* process environment > .env > selected YAML profile > code defaults
```

Select a profile with `MANNY_CONFIG_PROFILE`:

| Profile | Purpose |
| --- | --- |
| `configs/development.yaml` | Desktop simulator, mock hardware, local development |
| `configs/production.yaml` | Hardened device defaults and production storage |
| `configs/raspberrypi.yaml` | Raspberry Pi 5 hardware, local model, voice, kiosk |

Copy `.env.example` for desktop development. For a Pi installation, copy
`configs/raspberrypi.env.example` to `/opt/manny/.env` and edit it on the device. Never commit
the resulting `.env` file.

Important local services and default ports:

| Service | Address | Notes |
| --- | --- | --- |
| Manny API | `http://127.0.0.1:8765` | FastAPI, REST, WebSocket, and built UI |
| Vite UI | `http://127.0.0.1:5173` | Development-only simulator server |
| Ollama | `http://127.0.0.1:11434` | OpenAI-compatible local model endpoint, text and vision |
| Money Copilot MCP | configured HTTPS URL | Remote Streamable HTTP MCP server |

Example MCP configuration:

```env
MANNY_MCP_MODE=remote_http
MANNY_MCP_URL=https://expense-tracker-mcp.mcpize.run/mcp
MANNY_MCP_ALLOWED_TOOLS=get_budget_status,summarize_expenses
```

The allowlist must name the tools the *remote* server publishes, which is what
`RuleBasedAgent._tool_for` requests in `remote_http` mode. The semantic
`money.*` names belong to the bundled mock server (`mcp_servers/manny_local`) and
apply only in `mock` mode. Allowlisting a name the agent never requests, or one the
server does not publish, makes every finance answer come back as "that tool is not
approved on this device" — the policy is deny-by-default and does not fall back.

The MCP server performs OAuth discovery and uses PKCE with a localhost callback. Development
tokens are stored under ignored local data with restrictive permissions. Production hardware
must use secure device storage or the supported keyring backend.

To authorize a different Money Copilot account, use **Switch account** (or **Use another
account** while reconnecting) in the MCP panel and confirm the warning. Manny clears the old
OAuth authorization, finance cache, and conversational context before starting fresh OAuth;
local reminders and device settings are preserved.

## Local development

Requirements: Python 3.12 or newer, Node.js 20 or newer, and npm.

Linux/macOS:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
cd apps/ui && npm install && cd ../..
make dev
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Set-Location apps\ui
npm.cmd install
Set-Location ..\..
.\scripts\dev.ps1
```

`make dev` starts the API at `http://127.0.0.1:8765` and the live Vite simulator at
`http://127.0.0.1:5173`. A production UI build is served directly by the API on port 8765.

Useful commands:

| Command | Purpose |
| --- | --- |
| `make dev` | Start the development stack |
| `make run` | Start only the Manny FastAPI core |
| `make ui` | Start only the Vite development UI |
| `make mock-mcp` | Start the local deterministic MCP server |
| `make health` | Query runtime health |
| `make lint` | Run Python and UI linting |
| `make typecheck` | Run strict mypy and TypeScript checks |
| `make test` | Run the Python test suite |
| `make build` | Build the production UI |

### Local model on Windows

Install Ollama for Windows from its own installer, then:

```powershell
ollama pull gemma4:e2b
ollama serve
```

Ollama keeps its own model store outside the repository. The development profile uses the local
daemon when it answers and falls back to safe, deterministic behavior when it does not.

### Desktop camera and voice simulation

1. Start Manny and open the simulator in a Chromium-based browser.
2. Allow camera and microphone access when prompted.
3. Enable presence to test camera-driven present/idle transitions.
4. Select a language and use push-to-talk to test browser speech recognition or audio input.
5. Confirm the UI enters listening, thinking, and speaking states and returns to idle.
6. Disable camera/microphone permissions to verify honest privacy and unavailable states.

Browser support and installed operating-system voices differ. Use Pi Whisper/eSpeak validation
for the production offline voice path; browser voice is a simulator convenience.

## API surface

The source of truth is `apps/core/manny/api/routes.py`. The primary endpoints are:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Dependency and runtime health |
| GET | `/api/metrics` | Operational metrics |
| GET | `/api/state` | Current authoritative device state |
| GET | `/api/settings/public` | Non-secret client configuration |
| GET | `/api/mcp/status` | MCP authorization and connection state |
| POST | `/api/mcp/connect` | Begin or refresh MCP connection flow |
| POST | `/api/mcp/switch-account` | Clear account-specific state and start fresh OAuth |
| POST | `/api/agent/query` | Submit typed user input |
| POST | `/api/interaction/push-to-talk` | Start/stop a voice interaction |
| POST | `/api/interaction/voice/simulate` | Exercise voice behavior without hardware |
| POST | `/api/interaction/cancel` | Cancel the active interaction |
| POST | `/api/privacy/lock` | Enter privacy lock |
| GET/POST | `/api/reminders` | List or create reminders |
| POST | `/api/reminders/{id}/complete` | Complete a reminder |
| POST | `/api/device/reset` | Reset recoverable device state |
| WebSocket | `/api/ws` | State and event stream for the simulator/device UI |

Simulator-only presence, connectivity, and expression controls are also exposed in development
mode. Do not make them part of a production remote-control surface.

## Multilingual conversation and voice

Manny preserves the user's language across typed input, local transcription, agent routing,
finance-safe templates, API responses, and speech output. English, Bangla, Hindi, Mandarin
Chinese, Japanese, Spanish, French, German, Arabic, Portuguese, Russian, and Korean include
built-in finance wording. Other detected languages use locally generated placeholder-safe
wording, with English as the final fallback.

On Raspberry Pi, Whisper base provides automatic local language detection and eSpeak NG
provides broad offline speech output. Voice availability and pronunciation quality vary by
language, so production acceptance testing must cover every promised language on the actual
speaker and microphone hardware.

When adding a language:

1. Add normalization and finance-safe phrases in `apps/core/manny/i18n.py`.
2. Keep numeric values as formatter parameters; never embed model-produced finance values.
3. Add typed text and voice-path tests, including non-ASCII JSON transport.
4. Verify an installed TTS voice and pronunciation on the target device.
5. Document any quality limitation instead of silently switching languages.

## Raspberry Pi 5 installation

Use 64-bit Raspberry Pi OS with Python 3.12 or newer. Review every script before running it on
a device:

```bash
sudo ./scripts/bootstrap_pi.sh
sudo ./scripts/install_app_pi.sh
cd /opt/manny
sudo install -o manny -g manny -m 0600 configs/raspberrypi.env.example .env
sudoedit .env
sudo ./scripts/install_ollama_pi.sh
sudo ./scripts/install_multilingual_voice_pi.sh
sudo ./scripts/install_systemd.sh
sudo ./scripts/verify_hardware.sh
```

The app installer copies the reviewed source without credentials, local data, Git metadata, or
build caches. The Ollama installer requires explicit license confirmation, checksum-verifies its
source revision, and verifies the model checksum. Installation does not automatically authorize
MCP or enable services. After configuration and hardware verification, review and enable the
`manny-llm`, `manny-core`, and `manny-kiosk` systemd units as appropriate.

For deployment details and GPIO/device assumptions, see [docs/hardware.md](docs/hardware.md),
[docs/architecture.md](docs/architecture.md), and
[docs/troubleshooting.md](docs/troubleshooting.md).

## Validation and definition of done

Run the complete local gate before handing off code:

```bash
make lint
make typecheck
make test
make build
```

On Windows, use the equivalent `.venv` Python and `npm.cmd` commands if GNU Make is not
installed. Relevant focused tests should be run while developing; the full gate is still
required before release.

A change is done when:

- behavior matches the requirements and preserves the system invariants above;
- new logic has unit or integration coverage and boundary changes have contract coverage;
- Python remains strictly typed and TypeScript type checking passes;
- failure, offline, privacy, cancellation, and cache behavior are considered;
- configuration changes are reflected in every applicable profile and env template;
- documentation and API contracts are updated with the implementation;
- no secret, token, model, local database, generated build, or user financial data is staged;
- Raspberry Pi-dependent claims are marked unverified until tested on physical hardware.

## Coding-agent startup checklist

Use this sequence when beginning a new coding session:

1. Read this README plus `MANNY_OS_REQUIREMENTS.md`, `DECISIONS.md`, `ASSUMPTIONS.md`, and the
   relevant section of `ROADMAP.md`.
2. Inspect `git status` and `git diff` before editing. Preserve unrelated or unfinished user
   changes; never reset or overwrite them to obtain a clean tree.
3. Trace the requested behavior from its API/UI entry point through `lifecycle.py` into the
   owning service, state transition, and adapter boundary.
4. Search for existing tests and contracts before creating a new abstraction.
5. Implement the smallest coherent typed change and keep hardware or provider details behind
   the existing interfaces.
6. Test the normal path and at least the unavailable, invalid-data, cancellation, or privacy
   path that applies.
7. Run the validation gate and review the diff for secrets, demo finance data, unsafe tool
   exposure, and accidental generated files.
8. Update this README or the focused document when architecture, setup, API behavior, or an
   operational assumption changes.
9. Do not push, enable device services, rotate credentials, or perform destructive operations
   unless the user explicitly requests that action.

## Local data and secrets

| Path or value | Content | Git policy |
| --- | --- | --- |
| `.env` | Local endpoints, profile selection, device configuration | Ignored; never commit |
| `data/` | Models, OAuth state/tokens, databases, cache | Ignored; never commit |
| `logs/` | Runtime logs that may contain operational metadata | Ignored; never commit |
| `apps/ui/dist/` | Generated production UI | Generated; do not hand-edit |
| MCP credentials | Authorization material for the finance service | Never expose to UI or LLM |
| User financial values | MCP data or disclosed local cache | Never put in fixtures unless synthetic |

Use synthetic values in tests and screenshots. Avoid logging transcripts or finance payloads;
log stable event names and redacted diagnostic context instead.

## Known gates and limitations

- Physical Raspberry Pi 5 performance, thermals, microphone quality, speaker quality, camera
  placement, GPIO assignments, and kiosk recovery require hardware validation.
- Production OAuth token storage must use an accepted secure device backend.
- Recurring-payment features depend on the upstream MCP tool contract being available and
  validated; Manny must not infer them from unrelated data.
- Local model and multilingual voice latency varies by quantization, memory, cooling, language,
  and audio hardware.
- Browser speech recognition/synthesis is not the production offline voice implementation.
- Manny is a financial awareness companion, not a payment system or regulated financial adviser.

Track status and evidence in [ROADMAP.md](ROADMAP.md) and assumptions in
[ASSUMPTIONS.md](ASSUMPTIONS.md); do not delete a gate merely because simulator tests pass.

## Further documentation

- [docs/architecture.md](docs/architecture.md) — component boundaries and runtime design
- [docs/mcp-contract.md](docs/mcp-contract.md) — allowed finance tools and response contracts
- [docs/hardware.md](docs/hardware.md) — Raspberry Pi hardware expectations
- [docs/privacy.md](docs/privacy.md) — data handling and privacy behavior
- [docs/security.md](docs/security.md) — implementation security controls
- [docs/troubleshooting.md](docs/troubleshooting.md) — common setup and runtime failures
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution and review workflow
- [SECURITY.md](SECURITY.md) — project security policy and vulnerability reporting
- [CHANGELOG.md](CHANGELOG.md) — notable release changes
