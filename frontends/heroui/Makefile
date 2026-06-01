.PHONY: start stop install dev bridge chmod status help
.DEFAULT_GOAL := help

# Canonical ports — keep in sync with start.command
HEROUI_BRIDGE_PORT ?= 14169
HEROUI_UI_PORT     ?= 5178
# Other Vite ports that might leak from previous sessions
HEROUI_VITE_PORTS  ?= 5173 5174 5175 5176 5177 5179 5180

REPO_ROOT := $(shell cd ../.. && pwd)
SCRIPT_DIR := $(shell pwd)

help:
	@echo "GenericAgent HeroUI — make targets:"
	@echo "  make start    One-click: bridge + Vite UI (canonical entry)"
	@echo "  make stop     Kill anything on $(HEROUI_BRIDGE_PORT) / $(HEROUI_UI_PORT) / stray Vite ports"
	@echo "  make dev      Vite UI only (http://127.0.0.1:$(HEROUI_UI_PORT))"
	@echo "  make bridge   Python bridge only (port $(HEROUI_BRIDGE_PORT))"
	@echo "  make install  pnpm install"
	@echo "  make chmod    Restore +x on start.command / start.cmd (idempotent)"
	@echo "  make status   Show pids listening on bridge / UI ports"
	@echo "  make help     This help"

# Canonical one-click start. The chmod is defensive: even with
# core.fileMode=true, an outside `chmod 644` or filesystem reset
# would still kill the +x bit. This rule re-applies it on every run.
start: chmod
	@./start.command

dev: chmod
	@./node_modules/.bin/vite --host 127.0.0.1

bridge: chmod
	@cd "$(REPO_ROOT)" && python3 frontends/heroui/bridge.py

install:
	@command -v pnpm >/dev/null || { echo "pnpm not found — install via \`npm i -g pnpm\`" >&2; exit 1; }
	@pnpm install --prefer-offline

# Idempotent: re-applies +x safely. Safe to call from any rule.
chmod:
	@chmod +x start.command start.cmd 2>/dev/null || true

stop:
	@-lsof -ti :$(HEROUI_BRIDGE_PORT) 2>/dev/null | xargs -r kill -9 2>/dev/null
	@-lsof -ti :$(HEROUI_UI_PORT)     2>/dev/null | xargs -r kill -9 2>/dev/null
	@for p in $(HEROUI_VITE_PORTS); do \
		lsof -ti :$$p 2>/dev/null | xargs -r kill -9 2>/dev/null; \
	done
	@-pkill -f "frontends/heroui/bridge.py" 2>/dev/null
	@echo "stopped."

status:
	@printf "bridge (port %s): " "$(HEROUI_BRIDGE_PORT)"; \
		lsof -ti :$(HEROUI_BRIDGE_PORT) 2>/dev/null | tr '\n' ' ' | sed 's/ $$//'; echo
	@printf "ui     (port %s): " "$(HEROUI_UI_PORT)"; \
		lsof -ti :$(HEROUI_UI_PORT) 2>/dev/null | tr '\n' ' ' | sed 's/ $$//'; echo
