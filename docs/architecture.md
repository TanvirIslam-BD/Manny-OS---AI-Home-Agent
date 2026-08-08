# Phase 0 Architecture

The browser simulator communicates only with Manny Core's localhost REST and WebSocket API. Manny Core owns the authoritative state machine and controls hardware through interfaces. Phase 0 injects in-memory mock adapters, so the same runtime can execute on Windows, macOS, Linux, and CI.

```text
React/Vite simulator
       | REST + WebSocket
       v
FastAPI localhost service
       |
       +-- authoritative state machine
       +-- in-process event bus
       +-- typed configuration
       +-- hardware protocols
                 |
                 +-- mock camera/audio/LED/display
```

Money Copilot MCP and the tool-using agent are intentionally introduced in Phase 2. Current financial truth must never originate from the Phase 0 UI fixture.
