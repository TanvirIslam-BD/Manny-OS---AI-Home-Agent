# Product and Hardware Assumptions

The following remain unresolved and must not be encoded as permanent hardware facts:

- Final display manufacturer, native resolution, touch interface, and rotation are not selected.
- Final camera model, field of view, and enclosure position require validation.
- Final microphone array, speaker, amplifier, and selectable device identifiers are unknown.
- LED controller, rotary encoder, button, privacy switch, and GPIO mappings are unknown.
- The configured Money Copilot MCP server advertises OAuth 2.1 authorization with `mcp:tools`, `mcp:resources`, and `mcp:prompts`; production keyring provisioning and enclosure pairing still require device validation.
- The current MCP catalog has validated budget and spending schemas but no recurring-payment tool; recurring data remains unavailable rather than inferred.
- Moonshine, Kokoro, and Gemma 3 1B IT have adapters but still require Raspberry Pi 5 latency, memory, thermal, and accuracy benchmarks.
- Gemma 3 1B IT Q4_K_M is the conservative 8 GB Pi default; a larger model must not replace it until measured alongside simultaneous STT/TTS and camera workloads.
- Desktop development uses mock hardware while finance values come from validated MCP data; physical acceptance remains pending.
