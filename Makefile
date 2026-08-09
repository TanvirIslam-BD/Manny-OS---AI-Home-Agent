.PHONY: setup dev test test-routing lint typecheck ui run mock-mcp build install-pi install-app-pi install-ollama-pi install-voice-pi health

PYTHON ?= python
NPM ?= npm

setup:
	$(PYTHON) -m pip install -e ".[dev]"
	cd apps/ui && $(NPM) install

dev:
	$(PYTHON) scripts/dev.py

test:
	$(PYTHON) -m pytest

# Routing and finance-boundary cases against the real conversational model. Needs a
# served model, so it is not part of `test`. Run it before and after any edit to
# SYSTEM_INSTRUCTION and compare the score.
test-routing:
	MANNY_ROUTING_HARNESS=1 $(PYTHON) -m pytest tests/e2e/test_instruction_routing.py -v

lint:
	$(PYTHON) -m ruff check apps/core mcp_servers tests
	cd apps/ui && $(NPM) run lint

typecheck:
	$(PYTHON) -m mypy apps/core/manny
	cd apps/ui && $(NPM) run typecheck

ui:
	cd apps/ui && $(NPM) run dev -- --host 127.0.0.1

run:
	$(PYTHON) -m uvicorn manny.main:app --app-dir apps/core --host 127.0.0.1 --port 8765 --no-access-log

mock-mcp:
	$(PYTHON) -m mcp_servers.manny_local.server

build:
	cd apps/ui && $(NPM) run build

install-pi:
	./scripts/bootstrap_pi.sh

install-app-pi:
	./scripts/install_app_pi.sh

install-ollama-pi:
	./scripts/install_ollama_pi.sh

install-voice-pi:
	./scripts/install_multilingual_voice_pi.sh

health:
	$(PYTHON) scripts/health.py
