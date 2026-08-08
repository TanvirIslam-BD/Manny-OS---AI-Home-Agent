# Manny OS Architecture

```text
React/Vite display + desktop camera/microphone simulation
                     | REST + WebSocket
                     v
FastAPI localhost host runtime
  |-- authoritative state and privacy machine
  |-- half-duplex voice coordinator
  |-- swappable local intent, STT, and TTS adapters
  |-- deterministic policy and tool broker
  |-- official SDK MCP client and contract normalization
  |-- timestamped finance cache
  |-- presence and notification schedulers
  |-- reminders in SQLite
  `-- mockable camera/audio/LED/display adapters
```

Financial values enter through validated MCP structured results or timestamped cache. The official client keeps the authenticated MCP session open, while the broker coalesces duplicate dashboard requests and reuses fresh verified results. The model never receives OAuth credentials and cannot execute tools directly. Remote output is treated as untrusted data and normalized into local Pydantic contracts before presentation; the device UI has no hard-coded finance amounts.

Development injects deterministic fixtures. Raspberry Pi mode injects configurable Picamera2, ALSA, sysfs LED/display, Moonshine, and Kokoro adapters without fixed device identifiers.
