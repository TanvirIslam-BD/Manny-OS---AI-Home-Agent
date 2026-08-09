# Money Copilot MCP Contract

The semantic `money.*` contract in `MANNY_OS_REQUIREMENTS.md` is authoritative. Manny now connects through the official MCP Python SDK v2 over Streamable HTTP, performs OAuth discovery and PKCE authorization, and lists the remote catalog. Discovered tools are treated as untrusted and remain blocked until explicitly added to `MANNY_MCP_ALLOWED_TOOLS`.

The next agent phase will map approved server tools to Manny's typed finance schemas and deterministic policy engine. The UI fixture remains demo data and is never replaced with arbitrary MCP output.

## Transports

Only `mock` and `remote_http` exist. Streamable HTTP is what the wider ecosystem uses for clients that are not colocated with the server, which is Manny's situation on a device talking to Money Copilot.

Most open-source MCP servers ship stdio transport only, on the assumption that client and server share a machine. To use one of those, put a stdio-to-StreamableHTTP adapter in front of it and point `MANNY_MCP_URL` at the adapter; `supergateway` is the usual choice. That is preferable to implementing a second transport here, because the policy broker and allowlist should not have to care how bytes reach the server.

`local_stdio` and `local_http` were previously accepted configuration values that nothing implemented. Anything other than `remote_http` fell through to the mock client, so selecting them produced demo data that looked live. They are now rejected at validation.
