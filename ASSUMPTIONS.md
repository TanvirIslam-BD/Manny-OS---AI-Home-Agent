# Product and Hardware Assumptions

The following remain unresolved and must not be encoded as permanent hardware facts:

- Final display manufacturer, native resolution, touch interface, and rotation are not selected.
- Final camera model, field of view, and enclosure position require validation.
- Final microphone array, speaker, amplifier, and selectable device identifiers are unknown.
- LED controller, rotary encoder, button, privacy switch, and GPIO mappings are unknown.
- The configured Money Copilot MCP server advertises OAuth 2.1 authorization with `mcp:tools`, `mcp:resources`, and `mcp:prompts`; enclosure pairing still requires device validation.
- On-device token protection is bounded by hardware, not software. The Pi keeps OAuth material in a mode-0600 file because a headless appliance cannot hold a vault key anywhere the device itself cannot reach, and Pi 5 has no TPM or secure element to bind one to (ADR-013). Whether the enclosure gets such hardware is unresolved; until it does, physical possession of the device is possession of the Money Copilot session, and loss is handled by server-side revocation.
- The current MCP catalog has validated budget and spending schemas but no recurring-payment tool; recurring data remains unavailable rather than inferred.
- whisper.cpp base, eSpeak NG, Moonshine, Kokoro, and Gemma 3 1B IT have adapters but still require Raspberry Pi 5 latency, memory, thermal, pronunciation, and per-language accuracy benchmarks.
- Gemma 3 1B IT Q4_K_M is the device default for conversation, chosen for latency: the Pi 5 has no usable GPU offload, so generation is bound by memory bandwidth and 4B costs roughly three times as long per token. Its intent-routing accuracy at that size has not been measured against a labelled set of real utterances, and Qwen3 1.7B is the fallback if routing proves too weak — with Bengali and Hindi template quality to re-verify if it is adopted. 4B remains the choice for scene description, where the capability gap is real rather than a quality preference.
- Gemma, Whisper, eSpeak NG, and browser/OS voices cover different language sets. Text works wherever Gemma is capable; voice availability and quality depend on the installed runtime and voice, so “all languages” is broad best-effort coverage rather than a universal accuracy guarantee.
- Desktop development uses mock hardware while finance values come from validated MCP data; physical acceptance remains pending.
