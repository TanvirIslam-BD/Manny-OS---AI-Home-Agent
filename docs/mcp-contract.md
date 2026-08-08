# Money Copilot MCP Contract

The semantic `money.*` contract in `MANNY_OS_REQUIREMENTS.md` is authoritative. Manny now connects through the official MCP Python SDK v2 over Streamable HTTP, performs OAuth discovery and PKCE authorization, and lists the remote catalog. Discovered tools are treated as untrusted and remain blocked until explicitly added to `MANNY_MCP_ALLOWED_TOOLS`.

The next agent phase will map approved server tools to Manny's typed finance schemas and deterministic policy engine. The UI fixture remains demo data and is never replaced with arbitrary MCP output.
