---
title: Codebase Structure
focus: arch
generated_at: 2026-05-28
last_mapped_commit: 0741fd20140a70bbe4317edcf72b228e4c279422
---

# Codebase Structure

## Directory Layout

```text
GenericAgent/
├── agentmain.py                  # Main GenericAgent runtime, CLI, task/reflect modes
├── agent_loop.py                 # Central turn loop and tool dispatch/event emission
├── llmcore.py                    # LLM sessions, streaming parsers, text/native tool clients
├── ga.py                         # GenericAgentHandler and tool implementations
├── agent_streaming.py            # Model-visible stream filtering and summaries
├── TMWebDriver.py                # Browser automation support used by web tools
├── simphtml.py                   # Simplified HTML extraction for browser scans
├── launch.pyw                    # Desktop/webview launcher for Streamlit and optional bots
├── hub.pyw                       # Desktop hub launcher/window code
├── pyproject.toml                # Python package metadata and `ga` script entry
├── README.md                     # User-facing overview, install, usage, architecture notes
├── docs/                         # Installation/getting-started docs and superpowers plans/specs
├── assets/                       # Tool schemas, system prompts, templates, demos, browser extension assets
├── memory/                       # Global memory, SOPs, memory helper scripts, local memory stores
├── plugins/                      # Hook registry and optional tracing plugins
├── reflect/                      # Autonomous/reflect polling modes
├── frontends/                    # Streamlit, TUI, bot, desktop, ACP, HeroUI adapters
├── ga_cli/                       # Installed command dispatcher package
├── tests/                        # Python tests for core loop, streaming, HeroUI persistence/state
├── sche_tasks/                   # Scheduler task definitions and runtime scheduler state
├── ga_config/                    # Runtime config directory used by some frontends
├── temp/                         # Runtime logs, task I/O, model responses, generated artifacts
└── .planning/codebase/           # Generated GSD codebase maps
```

## Top-Level Runtime Files

| Path | Purpose | Maintainer guidance |
|---|---|---|
| `agentmain.py` | Main runtime object (`GenericAgent`), system prompt construction, task queue, CLI chat, `--task`, and `--reflect` modes. | Start here for runtime behavior, task lifecycle, LLM selection, and display queue semantics. |
| `agent_loop.py` | Execution loop: model call, stream filtering, tool dispatch, structured event emission, and loop stopping conditions. | Change turn sequencing, event names, hook timing, and tool result normalization here. |
| `llmcore.py` | Provider clients and sessions: Claude/OpenAI-compatible/native sessions, text-protocol/native tool clients, fallback sessions, prompt/response logs. | Add or modify model/provider behavior here; keep loop-facing `chat(messages, tools)` behavior compatible. |
| `ga.py` | `GenericAgentHandler`, filesystem/code/browser/user/memory tools, working-memory/plan-mode prompts. | Add model-callable tools here and keep schema files in `assets/` synchronized. |
| `agent_streaming.py` | Hides protocol/private tags and derives short summaries from model output. | Change display-visible filtering here, not in each UI. |
| `TMWebDriver.py` | Browser/CDP automation support used by `web_scan` / `web_execute_js`. | Browser-tool internals belong here or in adjacent browser helper modules. |
| `simphtml.py` | HTML simplification and body-content extraction. | Adjust page simplification behavior here. |
| `launch.pyw` | Starts Streamlit, optional bot/scheduler subprocesses, idle monitor, and webview window. | Desktop launcher features and process spawning belong here. |
| `hub.pyw` | Desktop hub/window entry. | Desktop hub-specific behavior belongs here. |
| `pyproject.toml` | Python package metadata, optional dependencies, and command script `ga = ga_cli.cli:main`. | Update package/runtime dependencies and CLI script registration here. |

## `frontends/` Structure

`frontends/` contains adapters. Most adapters import `agentmain.GeneraticAgent` / `GenericAgent`, start `agent.run()` in a background thread, submit prompts with `put_task()`, then render display queue updates.

```text
frontends/
├── chatapp_common.py             # Shared chat/bot adapter utilities and `AgentChatMixin`
├── stapp.py                      # Streamlit chat UI used by `launch.pyw`
├── tui_v3.py                     # Large prompt_toolkit/Rich terminal UI with typed AgentBridge events
├── tuiapp_v2.py                  # Textual/older terminal UI
├── tuiapp.py                     # Earlier TUI adapter
├── tgapp.py                      # Telegram adapter
├── fsapp.py                      # Feishu/Lark adapter
├── wechatapp.py                  # WeChat adapter
├── wecomapp.py                   # WeCom adapter
├── dingtalkapp.py                # DingTalk adapter
├── qqapp.py                      # QQ adapter
├── genericagent_acp_bridge.py    # ACP JSON-RPC stdio bridge
├── desktop_bridge.py             # Desktop bridge support
├── desktop_pet*.pyw              # Desktop pet UI variants
├── qtapp.py                      # Qt UI
├── dcapp.py                      # Desktop/chat adapter
├── conductor.py                  # Conductor frontend support
├── continue_cmd.py               # `/continue` frontend command integration
├── slash_cmds.py                 # Slash-command support
├── plan_state.py                 # Frontend plan state helpers
├── session_names.py              # Session naming helpers
├── review_cmd.py                 # Review command integration
├── export_cmd.py                 # Export/copy helpers
├── btw_cmd.py                    # Background task command integration
├── cost_tracker.py               # Cost tracking helper
├── desktop/                      # Tauri/static desktop frontend bundle
├── heroui/                       # React + aiohttp bridge full-stack frontend
└── skins/, *.png, *.gif          # Desktop pet/static UI assets
```

### Adapter Placement Rules

- Put reusable bot/chat behavior in `frontends/chatapp_common.py`.
- Put platform-specific message parsing, auth/allow-list, upload/download, rate-limit, and rendering logic in the adapter file: `frontends/tgapp.py`, `frontends/fsapp.py`, `frontends/wechatapp.py`, etc.
- Keep the boundary to core runtime as `GenericAgent.put_task()` plus display queue consumption. Do not call `agent_loop.agent_runner_loop()` directly from adapters unless implementing a new runtime kernel.
- Use existing command modules (`frontends/continue_cmd.py`, `frontends/review_cmd.py`, `frontends/btw_cmd.py`, `frontends/slash_cmds.py`) for cross-frontend commands rather than copying command parsing into each frontend.
- `frontends/tui_v3.py` is intentionally self-contained and large. New cross-UI logic should not be hidden inside it unless it is terminal-only.

## HeroUI Full-Stack Layout

```text
frontends/heroui/
├── bridge.py                     # AgentManager, aiohttp app wiring, turn threads, session lifecycle
├── bridge_core/
│   ├── session.py                # Session dataclass and default GA root / DB path discovery
│   ├── routes.py                 # HTTP/SSE/WS route handlers and static serving
│   ├── streaming.py              # WsHub, EventStreamHub, SSE formatting/cursors
│   ├── events.py                 # Raw agent event -> UI stream event conversion
│   ├── http_utils.py             # CORS, JSON helpers, request parsing
│   ├── titles.py                 # Chat title generation helpers
│   └── uploads.py                # Prompt/image upload normalization
├── session_store.py              # SQLite schema and load/upsert/delete methods
├── agent_state.py                # Capture/restore live agent continuation state
├── package.json                  # React/HeroUI/Tailwind/Vite dependencies and scripts
├── vite.config.ts                # Vite dev server and bridge proxy config
├── start.cmd                     # Windows launcher for bridge + Vite dev server
├── src/
│   ├── main.tsx                  # React entry
│   ├── App.tsx                   # Main app shell and high-level UI state
│   ├── api.ts                    # HTTP/SSE client and bridge response mapping
│   ├── state.ts                  # Stream event reducer and transcript/timeline builders
│   ├── types.ts                  # Frontend contract types
│   ├── ga_output_parser.ts       # Parser for GenericAgent text output artifacts/steps
│   ├── sop_prompt.ts             # SOP prompt helpers
│   ├── tool_details.ts           # Tool-card details mapping
│   ├── styles.css                # Tailwind/HeroUI/custom styling
│   ├── components/               # Composer, chat surface, conversation rail, SOP workspace
│   └── *.test.mjs                # Node/tsx tests for UI/event contracts
└── .data/                        # Runtime SQLite data directory; generated/runtime state
```

### HeroUI Placement Rules

- Put session/thread/runtime behavior in `frontends/heroui/bridge.py`.
- Put route parsing and HTTP response assembly in `frontends/heroui/bridge_core/routes.py`.
- Put raw-to-contract event conversion in `frontends/heroui/bridge_core/events.py`.
- Put WS/SSE queue mechanics in `frontends/heroui/bridge_core/streaming.py`.
- Put persistence schema and SQLite CRUD in `frontends/heroui/session_store.py`.
- Put live-agent state capture/restore in `frontends/heroui/agent_state.py`.
- Put React API calls in `frontends/heroui/src/api.ts` and state reduction in `frontends/heroui/src/state.ts`.
- Put visual components under `frontends/heroui/src/components/` and keep shared contract types in `frontends/heroui/src/types.ts`.

## `assets/` Structure

`assets/` contains runtime prompt/tool assets and user-facing media.

```text
assets/
├── tools_schema.json             # English/default model-callable tool schema
├── tools_schema_cn.json          # Chinese/localized tool schema
├── sys_prompt.txt                # Default system prompt
├── sys_prompt_en.txt             # English system prompt
├── insight_fixed_structure.txt   # Global memory structure injected by `ga.get_global_memory()`
├── insight_fixed_structure_en.txt
├── global_mem_insight_template*.txt
├── tool_usable_history.json
├── code_run_header.py
├── configure_mykey.py            # Configuration helper
├── supergrok_proxy.py            # Proxy/helper integration
├── agent_bbs.py                  # BBS/community helper
├── tmwd_cdp_bridge/              # Browser extension/CDP bridge assets
├── demo/                         # Demo GIFs/images referenced by README
└── images/                       # README/UI images and screenshots
```

### Asset Placement Rules

- Add or edit model-callable tool schemas in both `assets/tools_schema.json` and `assets/tools_schema_cn.json` when tool behavior changes.
- Add system-prompt changes in `assets/sys_prompt.txt` and `assets/sys_prompt_en.txt` when both languages are supported.
- Browser extension changes belong under `assets/tmwd_cdp_bridge/`.
- README/demo media belongs under `assets/demo/` or `assets/images/`.

## `memory/` Structure

`memory/` is a mixed runtime memory and SOP directory. It contains Markdown procedures, global memory files, helper scripts, and local memory stores.

Important files and areas:

| Path | Purpose |
|---|---|
| `memory/global_mem.txt` | Base global memory file initialized by `agentmain.py`. |
| `memory/global_mem_insight.txt` | Long-term insight content read by `ga.get_global_memory()`. |
| `memory/memory_management_sop.md` | SOP loaded by `start_long_term_update`. |
| `memory/plan_sop.md` | Plan-mode SOP referenced by handler prompts. |
| `memory/goal_mode_sop.md`, `memory/goal_hive_sop.md` | Goal/long-running task SOPs. |
| `memory/review_sop.md`, `memory/code_review_principles.md` | Review/code-quality SOPs. |
| `memory/tmwebdriver_sop.md`, `memory/vision_sop.md`, `memory/bb-browser_sop.md` | Browser/vision SOPs. |
| `memory/autonomous_operation_sop/` | Autonomous operation support docs and helper code. |
| `memory/L4_raw_sessions/` | Raw-session compression/archival support. |
| `memory/skill_search/` | Skill search package and `SKILL.md`. |
| `memory/frontend-slides/` | A local frontend-slides skill/materials directory. |
| `memory/.kg.sqlite3*`, `memory/.palace_db/` | Local/generated memory knowledge stores. |
| `memory/file_access_stats.json` | Runtime stats written by `ga.log_memory_access()`. |

### Memory Placement Rules

- Put reusable procedures as `memory/<topic>_sop.md` or under a focused subdirectory when multiple files are required.
- Keep executable helpers adjacent to their SOP only when the helper is memory-specific, as with `memory/autonomous_operation_sop/helper.py`.
- Do not treat generated databases (`memory/.kg.sqlite3*`, `memory/.palace_db/`) as source code.
- HeroUI SOP browsing/editing only exposes existing top-level `memory/*.md` files through `frontends/heroui/bridge_core/routes.py`.

## `plugins/` Structure

```text
plugins/
├── hooks.py                     # Global hook registry and plugin discovery
└── langfuse_tracing.py          # Optional Langfuse tracing plugin
```

Placement rules:

- Add new runtime plugins as non-underscore `plugins/*.py` files so `plugins.hooks.discover_and_load()` imports them.
- Register callbacks with `@hooks.register('<event>')` from `plugins/hooks.py`.
- Use available events from `agent_loop.py`: `agent_before`, `turn_before`, `llm_before`, `llm_after`, `turn_after`, `agent_after`, `tool_before`, `tool_after`.
- Keep optional dependency failures contained; `plugins/langfuse_tracing.py` self-disables when Langfuse config/imports are unavailable.

## `reflect/` and Scheduler Structure

```text
reflect/
├── goal_mode.py                 # Budgeted autonomous goal continuation mode
├── scheduler.py                 # Scheduled-task polling mode and port lock
├── agent_team_worker.py         # Agent-team worker helper
└── autonomous.py                # Minimal autonomous mode placeholder/entry

sche_tasks/
└── *.json                       # Scheduler task definitions
```

Placement rules:

- New reflect mode modules should expose `check()`, and may expose `init(args)`, `on_done(result)`, `INTERVAL`, and `ONCE`.
- Scheduler task definitions belong in `sche_tasks/`; completed/runtime scheduler outputs belong in scheduler-managed subpaths such as `sche_tasks/done/`.

## `ga_cli/` Structure

```text
ga_cli/
├── __init__.py
├── __main__.py                  # `python -m ga_cli` entry
├── cli.py                       # command dispatcher
├── ga_cli.cmd                   # Windows helper
└── ga-cli-install.cmd           # Windows install helper
```

`pyproject.toml` registers the installed command as `ga = ga_cli.cli:main`. Add new user-facing launch commands to `ga_cli/cli.py`; do not put package command behavior in root scripts unless it is also a direct runtime entry point.

## `docs/` Structure

```text
docs/
├── GETTING_STARTED.md
├── installation.md
├── installation_zh.md
├── macos_desktop_installation_zh.md
├── SETUP_FEISHU.md
└── superpowers/
    ├── specs/
    └── plans/
```

Use `docs/` for user/developer instructions. Keep runtime prompts and model/tool schemas in `assets/`, and keep agent-operational SOPs in `memory/`.

## `tests/` Structure

```text
tests/
├── test_agent_loop_events.py          # Structured event and tool-result behavior
├── test_agent_streaming.py            # Protocol tag filtering / visible stream behavior
├── test_llmcore_fast_ask.py           # Fast ask/session behavior
├── test_long_run_context.py           # Long-run context behavior
├── test_goal_mode.py                  # Reflect goal mode behavior
├── test_heroui_agent_state.py         # HeroUI agent state capture/restore/build
├── test_heroui_session_store.py       # HeroUI SQLite persistence
├── test_simple_http_server.py         # Simple HTTP server behavior
└── frontends/                         # Frontend-related tests directory
```

HeroUI frontend tests live next to the TypeScript implementation under `frontends/heroui/src/*.test.mjs`, including `state.test.mjs`, `tool_details.test.mjs`, `ui_contract.test.mjs`, `ga_bridge_contract.test.mjs`, `ga_output_parser.test.mjs`, `api_stream.test.mjs`, and `sop_prompt.test.mjs`.

### Test Placement Rules

- Put Python runtime tests under `tests/` with names `test_*.py`.
- Put HeroUI React/TypeScript contract tests next to the frontend source as `frontends/heroui/src/*.test.mjs`.
- Test core loop/event behavior at `tests/test_agent_loop_events.py` and stream filtering at `tests/test_agent_streaming.py` when changing `agent_loop.py` or `agent_streaming.py`.
- Test HeroUI persistence/state changes in `tests/test_heroui_session_store.py`, `tests/test_heroui_agent_state.py`, and the relevant `frontends/heroui/src/*.test.mjs` contract test.

## Naming and Organization Conventions

### Python

- Top-level core modules use short lowercase filenames: `ga.py`, `llmcore.py`, `agentmain.py`, `agent_loop.py`.
- Frontend adapter files usually end in `app.py` or identify a platform: `tgapp.py`, `fsapp.py`, `wechatapp.py`, `wecomapp.py`, `dingtalkapp.py`, `qqapp.py`, `stapp.py`.
- Model-callable tool methods are named `do_<tool_name>` in `ga.GenericAgentHandler`, and schema names in `assets/tools_schema*.json` must match the suffix.
- Runtime helper functions use snake_case. The legacy alias `GeneraticAgent = GenericAgent` is present in `agentmain.py` and imported by existing frontends.
- Reflect modules use simple module-level hooks: `init`, `check`, `on_done`, `INTERVAL`, `ONCE`.

### TypeScript / React

- HeroUI components are PascalCase files in `frontends/heroui/src/components/`: `ChatSurface.tsx`, `Composer.tsx`, `ConversationRail.tsx`, `SopWorkspace.tsx`.
- Non-component frontend modules are lowercase or descriptive: `api.ts`, `state.ts`, `types.ts`, `tool_details.ts`, `ga_output_parser.ts`, `sop_prompt.ts`.
- Frontend test files use `.test.mjs` next to the implementation.

### Runtime / Generated Directories

- `temp/` stores runtime model logs, task I/O, and temporary generated files; do not put source modules there.
- `__pycache__/`, `.pytest_cache/`, `frontends/heroui/.vite/`, and `frontends/heroui/.data/` are generated/runtime state.
- `.codegraph/` is the local code intelligence index.

## Where Maintainers Should Look

| Task | Start here | Also inspect |
|---|---|---|
| Change agent turn behavior | `agent_loop.py` | `tests/test_agent_loop_events.py`, `frontends/heroui/bridge_core/events.py`, `frontends/heroui/src/state.ts` |
| Add a model-callable tool | `ga.py` | `assets/tools_schema.json`, `assets/tools_schema_cn.json`, `tests/test_agent_loop_events.py` |
| Change model/provider support | `llmcore.py` | `agentmain.py`, `mykey_template.py`, `tests/test_llmcore_fast_ask.py` |
| Change prompt/global memory injection | `agentmain.py`, `ga.py` | `assets/sys_prompt*.txt`, `assets/insight_fixed_structure*.txt`, `memory/global_mem_insight.txt` |
| Change working-memory/plan behavior | `ga.py` | `memory/plan_sop.md`, `memory/memory_management_sop.md`, `tests/test_long_run_context.py` |
| Change stream sanitization | `agent_streaming.py` | `agent_loop.py`, `tests/test_agent_streaming.py`, `tests/test_agent_loop_events.py` |
| Add lifecycle instrumentation | `plugins/hooks.py` | `plugins/langfuse_tracing.py`, hook calls in `agent_loop.py` |
| Add/modify Streamlit UI | `frontends/stapp.py` | `launch.pyw`, `frontends/chatapp_common.py` |
| Add/modify terminal UI | `frontends/tui_v3.py` | `agentmain.py`, display queue contract in `agentmain.py` |
| Add/modify bot adapter | Matching `frontends/*app.py` | `frontends/chatapp_common.py`, platform config in `mykey_template.py` |
| Add ACP behavior | `frontends/genericagent_acp_bridge.py` | `agentmain.py`, ACP session methods in same file |
| Add HeroUI endpoint | `frontends/heroui/bridge_core/routes.py` | `frontends/heroui/bridge.py`, `frontends/heroui/src/api.ts` |
| Change HeroUI session persistence | `frontends/heroui/session_store.py` | `frontends/heroui/agent_state.py`, `tests/test_heroui_session_store.py` |
| Change HeroUI event contract | `frontends/heroui/bridge_core/events.py` | `frontends/heroui/src/types.ts`, `frontends/heroui/src/state.ts`, `frontends/heroui/src/*.test.mjs` |
| Change HeroUI visuals | `frontends/heroui/src/App.tsx`, `frontends/heroui/src/components/`, `frontends/heroui/src/styles.css` | `frontends/heroui/package.json` |
| Add reflect/autonomous mode | `reflect/` | `agentmain.py --reflect` path, `tests/test_goal_mode.py` |
| Add docs | `docs/` | `README.md`; use `memory/` only for operational SOPs |

## Evidence / Examples Inspected

Main files and directories inspected for this map:

- `.` root directory listing
- `pyproject.toml`
- `README.md`
- `agentmain.py`
- `agent_loop.py`
- `agent_streaming.py`
- `llmcore.py`
- `ga.py`
- `assets/`
- `assets/tools_schema.json`
- `memory/`
- `plugins/hooks.py`
- `plugins/langfuse_tracing.py`
- `reflect/`
- `reflect/goal_mode.py`
- `reflect/scheduler.py`
- `frontends/`
- `frontends/chatapp_common.py`
- `frontends/stapp.py`
- `frontends/tui_v3.py`
- `frontends/tgapp.py`
- `frontends/fsapp.py`
- `frontends/genericagent_acp_bridge.py`
- `frontends/desktop/`
- `frontends/heroui/`
- `frontends/heroui/bridge.py`
- `frontends/heroui/bridge_core/routes.py`
- `frontends/heroui/bridge_core/session.py`
- `frontends/heroui/bridge_core/streaming.py`
- `frontends/heroui/bridge_core/events.py`
- `frontends/heroui/session_store.py`
- `frontends/heroui/agent_state.py`
- `frontends/heroui/src/`
- `frontends/heroui/src/components/`
- `frontends/heroui/src/api.ts`
- `frontends/heroui/src/state.ts`
- `frontends/heroui/src/App.tsx`
- `frontends/heroui/package.json`
- `frontends/heroui/vite.config.ts`
- `frontends/heroui/start.cmd`
- `ga_cli/cli.py`
- `launch.pyw`
- `docs/`
- `tests/`

## Gaps / Unknowns

- No project-local `.claude/skills/` or `.agents/skills/` directory was present during mapping, so no project-specific skill placement rules were available.
- Secret/config files such as `mykey.py`, `mykey.txt`, `.env*`, and credential-like files were not inspected; structure guidance avoids secret contents.
- Runtime/generated contents under `temp/`, `frontends/heroui/.data/`, `frontends/heroui/.vite/`, `__pycache__/`, and `.pytest_cache/` were not treated as source structure.
- The Rust/Tauri internals under `frontends/desktop/src-tauri/` were identified but not deeply mapped; use that subtree when changing the desktop shell itself.
- Some platform adapters under `frontends/` were mapped by directory and shared patterns rather than exhaustive line-by-line review; inspect the specific adapter before modifying platform-specific authentication, media upload, or callback behavior.
