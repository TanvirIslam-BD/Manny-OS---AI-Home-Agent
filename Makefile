.PHONY: setup dev test lint typecheck ui run mock-mcp build install-pi install-app-pi install-gemma-pi health

PYTHON ?= python
NPM ?= npm

setup:
	$(PYTHON) -m pip install -e ".[dev]"
	cd apps/ui && $(NPM) install

dev:
	$(PYTHON) scripts/dev.py

test:
	$(PYTHON) -m pytest

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

install-gemma-pi:
	./scripts/install_gemma_pi.sh

health:
	$(PYTHON) scripts/health.py
