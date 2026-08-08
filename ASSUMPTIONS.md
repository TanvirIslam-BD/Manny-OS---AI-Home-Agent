# Product and Hardware Assumptions

The following remain unresolved and must not be encoded as permanent hardware facts:

- Final display manufacturer, native resolution, touch interface, and rotation are not selected.
- Final camera model, field of view, and enclosure position require validation.
- Final microphone array, speaker, amplifier, and selectable device identifiers are unknown.
- LED controller, rotary encoder, button, privacy switch, and GPIO mappings are unknown.
- The configured Money Copilot MCP server advertises OAuth 2.1 authorization with `mcp:tools`, `mcp:resources`, and `mcp:prompts`; the final production secure-token store and enclosure pairing experience remain pending.
- Local model, STT, and TTS backends must be benchmarked on Raspberry Pi 5 before selection.
- Phase 0 uses mock hardware and explicitly labelled simulated finance values.
