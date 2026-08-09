# Manny OS Architecture

```text
React/Vite display + desktop camera/microphone simulation
                     | REST + WebSocket
                     v
FastAPI localhost host runtime
  |-- authoritative state and privacy machine
  |-- half-duplex voice coordinator
  |-- swappable local model, STT, and TTS adapters
  |-- deterministic policy and tool broker
  |-- official SDK MCP client and contract normalization
  |-- timestamped finance cache
  |-- presence and notification schedulers
  |-- reminders in SQLite
  `-- mockable camera/audio/LED/display adapters
```

Financial values enter through validated MCP structured results or timestamped cache. The official client keeps the authenticated MCP session open, while the broker coalesces duplicate dashboard requests and reuses fresh verified results. The model never receives OAuth credentials and cannot execute tools directly. Remote output is treated as untrusted data and normalized into local Pydantic contracts before presentation; the device UI has no hard-coded finance amounts.

The Pi profile serves `gemma4:e2b` from Ollama on loopback, hardened through a systemd drop-in (ADR-020). Manny asks it for a schema-constrained decision containing a BCP-47 language tag and either a same-language general reply or one approved finance intent. For finance, the model can return only a placeholder template; deterministic host code validates its exact fields and inserts MCP values afterward. Pydantic validates the response, allows one repair attempt, and falls back to deterministic behavior if the local model is unavailable. Only recent non-financial dialogue is kept in volatile memory.

Multilingual Raspberry Pi voice uses whisper.cpp base with automatic language detection and eSpeak NG with the detected language voice. The response language travels through the coordinator so speech output matches the transcript. Development injects deterministic fixtures; browser simulation provides an explicit locale selector because browser speech recognition does not guarantee automatic language detection. Raspberry Pi mode injects configurable Picamera2, ALSA, sysfs LED/display, STT, and TTS adapters without fixed device identifiers.
