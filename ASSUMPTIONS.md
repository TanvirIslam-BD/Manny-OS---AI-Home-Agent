# Product and Hardware Assumptions

The following remain unresolved and must not be encoded as permanent hardware facts:

- Final display manufacturer, native resolution, touch interface, and rotation are not selected.
- Final camera model, field of view, and enclosure position require validation.
- Final microphone array, speaker, amplifier, and selectable device identifiers are unknown.
- LED controller, rotary encoder, button, privacy switch, and GPIO mappings are unknown.
- The configured Money Copilot MCP server advertises OAuth 2.1 authorization with `mcp:tools`, `mcp:resources`, and `mcp:prompts`; production keyring provisioning and enclosure pairing still require device validation.
- The current MCP catalog has validated budget and spending schemas but no recurring-payment tool; recurring data remains unavailable rather than inferred.
- whisper.cpp base, eSpeak NG, Moonshine, Kokoro, and Gemma 3 1B IT have adapters but still require Raspberry Pi 5 latency, memory, thermal, pronunciation, and per-language accuracy benchmarks.
- Gemma 3 4B IT Q4_K_M is now the device default so the camera view can be described locally; it has not yet been measured alongside simultaneous STT/TTS and camera workloads, and 1B remains the fallback if it does not fit.
- Gemma, Whisper, eSpeak NG, and browser/OS voices cover different language sets. Text works wherever Gemma is capable; voice availability and quality depend on the installed runtime and voice, so “all languages” is broad best-effort coverage rather than a universal accuracy guarantee.
- Desktop development uses mock hardware while finance values come from validated MCP data; physical acceptance remains pending.
