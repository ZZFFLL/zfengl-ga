---
title: Technology Stack
focus: tech
generated_at: 2026-05-28
last_mapped_commit: 0741fd20140a70bbe4317edcf72b228e4c279422
---

# Technology Stack

## Repository Shape

GenericAgent is a Python-first autonomous agent framework with multiple optional frontends and adapters. The root runtime is driven by `agentmain.py`, `agent_loop.py`, `llmcore.py`, and `ga.py`. Frontend adapters live under `frontends/`, the HeroUI React application lives under `frontends/heroui/`, and the Tauri/static desktop shell lives under `frontends/desktop/`.

No root `package.json`, `requirements.txt`, `.nvmrc`, `.python-version`, `pytest.ini`, or `eslint.config.js` was detected. The authoritative Python packaging manifest is `pyproject.toml`; JavaScript/TypeScript manifests are scoped to frontend subdirectories.

## Languages

**Primary: Python**
- Runtime package metadata is in `pyproject.toml` with `requires-python = ">=3.10,<3.14"`.
- Installation docs recommend Python 3.11 or 3.12 and explicitly warn against Python 3.14 in `docs/installation.md` and `docs/GETTING_STARTED.md`.
- Core execution, LLM protocol handling, tools, frontends, plugins, and test coverage are Python: `agentmain.py`, `agent_loop.py`, `llmcore.py`, `ga.py`, `frontends/*.py`, `plugins/*.py`, `tests/*.py`.

**Frontend languages: TypeScript, TSX, JavaScript**
- HeroUI full-stack UI uses TypeScript/React in `frontends/heroui/src/*.ts` and `frontends/heroui/src/*.tsx`.
- HeroUI tests use JavaScript modules with Node's built-in test runner through `tsx`, for example `frontends/heroui/src/state.test.mjs`.
- Desktop/static UI uses plain browser JavaScript in `frontends/desktop/static/app.js` and `frontends/desktop/static/ga-web.js`.
- Browser automation extension code is JavaScript in `assets/tmwd_cdp_bridge/background.js` and `assets/tmwd_cdp_bridge/content.js`.

**Desktop shell language: Rust**
- Tauri v2 desktop wrapper code lives under `frontends/desktop/src-tauri/`.
- Rust package metadata is in `frontends/desktop/src-tauri/Cargo.toml`; lockfile is `frontends/desktop/src-tauri/Cargo.lock`.

**Configuration/data formats**
- TOML: `pyproject.toml`, `frontends/desktop/src-tauri/Cargo.toml`.
- JSON: `assets/tools_schema.json`, `assets/tools_schema_cn.json`, `frontends/desktop/src-tauri/tauri.conf.json`.
- YAML: `frontends/heroui/pnpm-lock.yaml`.
- Markdown SOPs and docs: `memory/*.md`, `docs/*.md`, `README.md`.

## Python Runtime and Packaging

**Package manifest:** `pyproject.toml`
- Project name/version: `genericagent` `0.1.0`.
- Build backend: `setuptools.build_meta` with `setuptools>=68.0`.
- Installed package: `ga_cli` via `[tool.setuptools] packages = ["ga_cli"]`.
- Console script: `ga = "ga_cli.cli:main"`.

**Core dependencies declared in `pyproject.toml`:**
- `requests>=2.28` — HTTP clients for LLM APIs, bot APIs, browser/CDP helpers, and probe scripts.
- `beautifulsoup4>=4.12` — HTML simplification in `simphtml.py`.
- `bottle>=0.12` — TMWebDriver local HTTP bridge in `TMWebDriver.py`.
- `simple-websocket-server>=0.4` — TMWebDriver WebSocket server in `TMWebDriver.py`.
- `aiohttp>=3.9` — HeroUI and desktop bridge HTTP/WebSocket/SSE servers in `frontends/heroui/bridge.py`, `frontends/heroui/bridge_core/routes.py`, and `frontends/desktop_bridge.py`.

**Optional UI dependencies declared in `pyproject.toml` `[project.optional-dependencies].ui`:**
- `streamlit>=1.28` — Streamlit app in `frontends/stapp.py`.
- `pywebview>=4.0` — desktop webview launcher in `launch.pyw`.
- `textual>=0.70` and `rich>=13.0` — TUI v2 in `frontends/tuiapp_v2.py`; TUI v3 uses `rich` in `frontends/tui_v3.py`.
- `prompt_toolkit>=3.0,<4` — declared for the scrollback-first TUI generation even though the inspected `frontends/tui_v3.py` imports `rich` directly.
- `pillow>=9.0` — image handling in UI/vision flows including `memory/vision_api.template.py`, `frontends/wechatapp.py`, and UI support.

**Optional bot/frontend dependencies declared in `pyproject.toml` `[project.optional-dependencies].all-frontends`:**
- `python-telegram-bot>=20.0` for `frontends/tgapp.py`.
- `qq-botpy>=1.0` for `frontends/qqapp.py`.
- `pycryptodome>=3.19` and `qrcode>=7.4` for WeChat/iLink crypto and QR login in `frontends/wechatapp.py`.
- `lark-oapi>=1.0` for Feishu in `frontends/fsapp.py`.
- `wecom-aibot-sdk>=1.0` for WeCom in `frontends/wecomapp.py`.
- `dingtalk-stream>=0.20` for DingTalk in `frontends/dingtalkapp.py`.

**Notable optional/imported dependencies not declared in `pyproject.toml`:**
- `PySide6` is required by the Qt frontend `frontends/qtapp.py` according to its module docstring/imports.
- `markdown` is optional for `frontends/qtapp.py` according to its module docstring.
- `discord.py` is required by `frontends/dcapp.py` but is not included in `all-frontends`.
- `langfuse` is required only if `plugins/langfuse_tracing.py` self-activates from `langfuse_config`.
- `ultralytics`, `rapidocr-onnxruntime`, `numpy`, and `pillow` are required by `memory/ui_detect.py`.
- `psutil` is imported lazily by `ga_cli/cli.py` for `ga status`.
- `pytest` is not declared, but the repository contains pytest-compatible tests under `tests/`.

## JavaScript/TypeScript Frontend Stack

**HeroUI app manifest:** `frontends/heroui/package.json`
- Package manager evidence: `frontends/heroui/pnpm-lock.yaml` lockfile uses lockfile version `9.0`.
- Scripts:
  - `pnpm dev` → `vite --host 127.0.0.1`.
  - `pnpm build` → `tsc --noEmit && vite build`.
  - `pnpm test` → `tsx --test` over `src/*.test.mjs` files.
- Runtime dependencies:
  - `react`/`react-dom` `^19.2.1` in `package.json`; lockfile resolves `19.2.6`.
  - `@heroui/react` and `@heroui/styles` `^3.1.0`.
  - `tailwindcss` `^4.3.0`, `@tailwindcss/postcss` `^4.3.0`, `postcss` `^8.5.15`.
  - `motion` `^12.40.0`, `lucide-react` `^0.561.0`, `tailwind-variants` `^3.2.2`.
  - Markdown rendering via `react-markdown` `^10.1.0` and `remark-gfm` `^4.0.1`.
- Dev dependencies:
  - `typescript` `^5.9.3`, `vite` `^7.3.2`, `@vitejs/plugin-react` `^5.1.1`, `tsx` `^4.21.0`, React type packages.

**HeroUI TypeScript configuration:** `frontends/heroui/tsconfig.json`
- `target: ES2022`, `module: ESNext`, `jsx: react-jsx`, `strict: true`, `noEmit: true`.
- Includes only `src`.

**HeroUI Vite configuration:** `frontends/heroui/vite.config.ts`
- Dev server host is `127.0.0.1`, port `5178`.
- Proxies `/status`, `/config`, `/model-profile`, `/model-profiles`, `/sessions`, `/session`, `/sops`, `/path`, and `/ws` to `GA_HEROUI_API_TARGET` or `http://127.0.0.1:14169`.

**HeroUI PostCSS/Tailwind:** `frontends/heroui/postcss.config.mjs`
- Uses `@tailwindcss/postcss`, matching Tailwind CSS v4.

## Desktop/Tauri Stack

**Desktop static shell:** `frontends/desktop/static/`
- Plain HTML/CSS/JS static application: `frontends/desktop/static/index.html`, `frontends/desktop/static/app.js`, `frontends/desktop/static/styles.css`.
- Browser-side bridge adapter hardcodes the local desktop bridge at `http://<host>:14168` and `ws://<host>:14168/ws` in `frontends/desktop/static/ga-web.js`.

**Tauri manifest:** `frontends/desktop/package.json`
- Defines `genericagent-web2` with a single `tauri` script.
- Dev dependency: `@tauri-apps/cli` `^2`.

**Rust/Tauri manifest:** `frontends/desktop/src-tauri/Cargo.toml`
- Rust edition `2021`.
- `tauri = { version = "2", features = ["devtools"] }`.
- `tauri-plugin-single-instance = "2"`, `serde`, `serde_json`, `dirs`.
- Build dependency: `tauri-build = "2"`.

**Tauri app config:** `frontends/desktop/src-tauri/tauri.conf.json`
- Product `GenericAgent`, version `0.1.0`, identifier `com.genericagent.app`.
- `frontendDist` points to `../static`.
- CSP is disabled with `"csp": null`.
- Bundles target `nsis` and `dmg`.

## Build and Run Entry Points

**Python CLI:**
- `ga` shell wrappers: `ga`, `ga.cmd`, and `fsapp_service.bat`.
- `ga.cmd` runs `python -m ga_cli %*`, preferring `.venv\Scripts\python.exe` when present.
- Command dispatcher is `ga_cli/cli.py`; it launches `agentmain.py`, `launch.pyw`, `hub.pyw`, and frontends under `frontends/`.

**Core agent:**
- CLI/REPL entrypoint: `agentmain.py`.
- Agent loop and tool protocol: `agent_loop.py`.
- LLM sessions/protocols: `llmcore.py`.
- Tool handlers and browser/file/code operations: `ga.py`.

**Python UI/frontends:**
- Streamlit app: `frontends/stapp.py` launched by `launch.pyw` or `ga_cli/cli.py`.
- PyWebView wrapper: `launch.pyw`.
- Tkinter launcher: `hub.pyw`.
- TUI v2/v3: `frontends/tuiapp_v2.py`, `frontends/tui_v3.py`.
- Qt/PySide UI: `frontends/qtapp.py`.
- Desktop local HTTP bridge: `frontends/desktop_bridge.py`.
- HeroUI Python bridge: `frontends/heroui/bridge.py`.

**HeroUI one-click start:**
- `frontends/heroui/start.cmd` starts `python frontends\heroui\bridge.py`, waits, then starts `pnpm dev`.
- Default HeroUI bridge target is `http://127.0.0.1:14169`; default Vite URL is `http://127.0.0.1:5178`.

## Test Tools

**Python tests:**
- Tests are under `tests/`, with `unittest` style in `tests/test_llmcore_fast_ask.py`, `tests/test_simple_http_server.py`, and pytest-compatible `test_*` functions in files such as `tests/test_heroui_session_store.py`.
- Tests patch dependencies directly with `unittest.mock`, load modules by path with `importlib.util`, and use `tmp_path` in pytest-style tests.
- No project-level pytest config or test dependency declaration was detected.

**HeroUI/TypeScript tests:**
- `frontends/heroui/package.json` runs `tsx --test` with Node's built-in `node:test` and `node:assert/strict`.
- Examples include `frontends/heroui/src/state.test.mjs`, `frontends/heroui/src/api_stream.test.mjs`, and `frontends/heroui/src/ga_bridge_contract.test.mjs`.

**Build checks:**
- HeroUI build uses `tsc --noEmit` plus `vite build` through `frontends/heroui/package.json`.
- Tauri build is available via `frontends/desktop/package.json` script `tauri`, backed by `frontends/desktop/src-tauri/Cargo.toml`.

## Configuration Sources

**Secrets and model configuration:**
- `llmcore.py` loads `mykey.py` from Python import path and falls back to `mykey.json` beside `llmcore.py`.
- `mykey.py` is ignored by `.gitignore`; it must not be committed.
- Templates are `mykey_template.py` and `mykey_template_en.py`.
- Interactive configuration helper is `assets/configure_mykey.py`.

**Runtime environment variables:**
- `GA_LANG` controls English/Chinese prompt and UI behavior in `agentmain.py`, `frontends/stapp.py`, `frontends/tui_v3.py`, and `llmcore.py`.
- `GA_WORKSPACE_ROOT` and `GA_USER_DATA_DIR` are used by `frontends/fsapp.py` to locate workspace and config directories.
- `BRIDGE_HOST`, `BRIDGE_PORT`, `HEROUI_BRIDGE_PORT`, and `HEROUI_BRIDGE_DB` configure bridge network/database behavior in `frontends/heroui/bridge.py` and `frontends/desktop_bridge.py`.
- `GA_HEROUI_API_TARGET` configures HeroUI frontend proxying in `frontends/heroui/vite.config.ts`, `frontends/heroui/README.md`, and `frontends/heroui/start.cmd`.

**Local data/config directories:**
- `ga_config/` is used by Feishu workspace config discovery in `frontends/fsapp.py`.
- `memory/` contains SOPs and operational memory; `.gitignore` tracks selected SOPs while ignoring general memory files.
- `temp/` stores runtime logs, model responses, media, and bridge state; `.gitignore` ignores it.
- `frontends/heroui/.data/sessions.sqlite3` is the default HeroUI session database path from `frontends/heroui/bridge_core/session.py`.

## Evidence and Examples Inspected

- `pyproject.toml`
- `README.md`
- `docs/installation.md`
- `docs/GETTING_STARTED.md`
- `frontends/heroui/package.json`
- `frontends/heroui/pnpm-lock.yaml`
- `frontends/heroui/tsconfig.json`
- `frontends/heroui/vite.config.ts`
- `frontends/heroui/postcss.config.mjs`
- `frontends/heroui/start.cmd`
- `frontends/heroui/README.md`
- `frontends/desktop/package.json`
- `frontends/desktop/src-tauri/Cargo.toml`
- `frontends/desktop/src-tauri/tauri.conf.json`
- `frontends/desktop/static/ga-web.js`
- `agentmain.py`
- `agent_loop.py`
- `llmcore.py`
- `ga.py`
- `ga_cli/cli.py`
- `launch.pyw`
- `hub.pyw`
- `frontends/stapp.py`
- `frontends/tuiapp_v2.py`
- `frontends/tui_v3.py`
- `frontends/qtapp.py`
- `frontends/heroui/bridge.py`
- `frontends/heroui/session_store.py`
- `frontends/desktop_bridge.py`
- `TMWebDriver.py`
- `plugins/langfuse_tracing.py`
- `tests/test_llmcore_fast_ask.py`
- `tests/test_heroui_session_store.py`
- `frontends/heroui/src/state.test.mjs`
- `.gitignore`

## Gaps and Unknowns

- No root `requirements.txt` was detected; dependency truth is split between `pyproject.toml`, optional imports, docs, and frontend manifests.
- No root `package.json` was detected; JavaScript tooling is scoped to `frontends/heroui/` and `frontends/desktop/`.
- No `.nvmrc` or equivalent Node version pin was detected; Node compatibility is inferred from Vite/TypeScript/HeroUI package versions only.
- No `.python-version` was detected; supported Python versions are from `pyproject.toml` and docs.
- No lint/format configuration was detected for Python or TypeScript in inspected config files.
- Some imported optional packages are not declared in `pyproject.toml` (`PySide6`, `discord.py`, `langfuse`, `ultralytics`, `rapidocr-onnxruntime`, `numpy`, `psutil`). Install them only when using the corresponding feature.
- `tests/test_simple_http_server.py` references `simple_http_server`, but no `simple_http_server.py` file appeared in the live root listing or CodeGraph index.
