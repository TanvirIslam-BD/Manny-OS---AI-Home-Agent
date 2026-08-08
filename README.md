# Manny OS

Manny OS is the application stack for **Manny Copilot**, a stationary AI home and desk assistant powered by Money Copilot AI. This repository implements the desktop-simulated software phases in `MANNY_OS_REQUIREMENTS.md`; physical Raspberry Pi validation gates are tracked separately.

## What works

- Responsive Manny device simulator with animated idle, present, listening, thinking, speaking, alert, offline, muted, camera-disabled, and error states
- FastAPI service with health, public configuration, runtime state, simulator controls, and a WebSocket event stream
- Official MCP Python SDK v2 client for Streamable HTTP and OAuth 2.1 account authorization
- Safe MCP status/tool discovery with an explicit tool allowlist before any tool can execute
- Live device dashboard populated from validated MCP budget and category summaries, with refresh and offline-cache labels
- One authoritative, validated application state machine
- Typed settings loaded from defaults, YAML profiles, and `MANNY_*` environment variables
- Mock camera, microphone, speaker, LED, and display adapters
- Unit and API tests that run without Raspberry Pi hardware

The finance display contains no hard-coded amounts. It shows setup/loading/unavailable states until validated MCP data arrives; cached answers disclose their last-sync time.

## Money Copilot MCP

Configure the endpoint outside source control:

```env
MANNY_MCP_MODE=remote_http
MANNY_MCP_URL=https://your-money-copilot.example/mcp
MANNY_MCP_ALLOWED_TOOLS=money.get_budget_summary,money.get_transactions
```

Open the simulator and select **Authorize**. Manny uses OAuth discovery, PKCE, dynamic client registration, and a localhost callback. Development tokens are stored under the ignored `data/` directory with restrictive file permissions; production hardware must replace this with secure device storage.

## Quick start

Requirements: Python 3.12+, Node.js 20+, and npm.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
cd apps/ui && npm install && cd ../..
make dev
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Set-Location apps\ui
npm.cmd install
Set-Location ..\..
.\scripts\dev.ps1
```

The API is available at `http://127.0.0.1:8765`; Vite serves the simulator at `http://127.0.0.1:5173`.

## Validation

```bash
make lint
make typecheck
make test
make build
```

## Current status

The simulator covers UI, agent/MCP, voice, vision, reminders/alerts, device adapters, and hardening. See [ROADMAP.md](ROADMAP.md) for physical hardware, production-key, and upstream recurring-payment contract gates.

## Safety and privacy

- Manny does not expose payment, transfer, or trading actions.
- Hardware is accessed only through replaceable adapters.
- The local API binds to loopback by default.
- Face recognition is disabled by default.
- Secrets, device data, and local databases are excluded from Git.

Read [MANNY_OS_REQUIREMENTS.md](MANNY_OS_REQUIREMENTS.md), [DECISIONS.md](DECISIONS.md), and [ASSUMPTIONS.md](ASSUMPTIONS.md) before architectural or feature changes.
