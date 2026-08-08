# Manny OS

Manny OS is the application stack for **Manny Copilot**, a stationary AI home and desk assistant powered by Money Copilot AI. This repository implements the desktop-simulated software phases in `MANNY_OS_REQUIREMENTS.md`; physical Raspberry Pi validation gates are tracked separately.

## What works

- Responsive Manny device simulator with animated idle, present, listening, thinking, speaking, alert, offline, muted, camera-disabled, and error states
- FastAPI service with health, public configuration, runtime state, simulator controls, and a WebSocket event stream
- Official MCP Python SDK v2 client for Streamable HTTP and OAuth 2.1 account authorization
- Safe MCP status/tool discovery with an explicit tool allowlist before any tool can execute
- Live device dashboard populated from validated MCP budget and category summaries, with refresh and offline-cache labels
- Local Gemma 3 1B IT conversational agent through a loopback-only llama.cpp server, with short in-memory context and deterministic fallback
- One authoritative, validated application state machine
- Typed settings loaded from defaults, YAML profiles, and `MANNY_*` environment variables
- Mock camera, microphone, speaker, LED, and display adapters
- Unit and API tests that run without Raspberry Pi hardware

The finance display contains no hard-coded amounts. It shows setup/loading/unavailable states until validated MCP data arrives; cached answers disclose their last-sync time.

## Local Gemma companion

Raspberry Pi and production profiles use `gemma-3-1b-it-Q4_K_M.gguf` through `llama-server` on `127.0.0.1:8080`. The model handles friendly general conversation and natural-language intent routing. It never receives MCP credentials or executes tools; financial facts still pass through the policy broker and validated MCP contracts.

On a reviewed Raspberry Pi installation:

```bash
sudo ./scripts/bootstrap_pi.sh
sudo ./scripts/install_app_pi.sh
cd /opt/manny
sudo install -o manny -g manny -m 0600 configs/raspberrypi.env.example .env
sudoedit .env
sudo ./scripts/install_gemma_pi.sh
sudo ./scripts/install_systemd.sh
```

Use 64-bit Raspberry Pi OS with Python 3.12 or newer. The app installer copies the
reviewed tree without `.env`, credentials, local data, Git metadata, or build caches, then
creates the virtual environment and production UI. The Gemma installer requires explicit
license confirmation, pins the llama.cpp source ref, verifies the 806 MB model's SHA-256
checksum, and does not enable services automatically. Copy and edit `.env.example` as
`/opt/manny/.env` with the real timezone and MCP endpoint, run
`scripts/verify_hardware.sh`, and enable services only after review.

For the Windows desktop simulator:

```powershell
.\scripts\install_gemma_windows.ps1
.\scripts\start_gemma_windows.ps1
```

Both the pinned runtime and model remain in the ignored `data/` directory. The development profile connects to the loopback server automatically and falls back safely when it is not running.

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
