# Manny OS

Manny OS is the application stack for **Manny Copilot**, a stationary AI home and desk assistant powered by Money Copilot AI. This repository currently implements the Phase 0 development scaffold and browser simulator defined by `MANNY_OS_REQUIREMENTS.md`.

## What works

- Responsive Manny device simulator with animated idle, present, listening, thinking, speaking, alert, offline, muted, camera-disabled, and error states
- FastAPI service with health, public configuration, runtime state, simulator controls, and a WebSocket event stream
- Official MCP Python SDK v2 client for Streamable HTTP and OAuth 2.1 account authorization
- Safe MCP status/tool discovery with an explicit tool allowlist before any tool can execute
- One authoritative, validated application state machine
- Typed settings loaded from defaults, YAML profiles, and `MANNY_*` environment variables
- Mock camera, microphone, speaker, LED, and display adapters
- Unit and API tests that run without Raspberry Pi hardware

All finance values currently shown in the simulator are visibly marked as demo data. Connecting the configured Money Copilot server discovers its tools, but the simulator does not present them as financial truth until the Phase 2 agent and validated finance schemas are implemented.

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

## Current phase

Phase 0 is complete, and the remote MCP connectivity slice is implemented. See [ROADMAP.md](ROADMAP.md) for the agent, validated finance flows, voice, vision, and Raspberry Pi device work that follows.

## Safety and privacy

- Manny does not expose payment, transfer, or trading actions.
- Hardware is accessed only through replaceable adapters.
- The local API binds to loopback by default.
- Face recognition is disabled by default.
- Secrets, device data, and local databases are excluded from Git.

Read [MANNY_OS_REQUIREMENTS.md](MANNY_OS_REQUIREMENTS.md), [DECISIONS.md](DECISIONS.md), and [ASSUMPTIONS.md](ASSUMPTIONS.md) before architectural or feature changes.
