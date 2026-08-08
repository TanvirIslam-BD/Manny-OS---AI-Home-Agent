# Contributing

Read `MANNY_OS_REQUIREMENTS.md`, `DECISIONS.md`, `ASSUMPTIONS.md`, and `ROADMAP.md` before changing the architecture.

Keep changes scoped to one roadmap phase or issue. Add tests for new behavior. Before submitting a change, run:

```bash
make lint
make typecheck
make test
make build
```

Do not commit secrets, local device data, generated build output, or hardware identifiers.
