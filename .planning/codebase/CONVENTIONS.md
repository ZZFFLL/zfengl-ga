---
title: Coding Conventions
focus: quality
generated_at: 2026-05-28
last_mapped_commit: 0741fd20140a70bbe4317edcf72b228e4c279422
---

# Coding Conventions

## Scope

This document maps coding conventions, error handling, state/concurrency patterns, import style, logging style, and frontend conventions for GenericAgent. Use these patterns when changing core Python files such as `agentmain.py`, `agent_loop.py`, `ga.py`, `llmcore.py`, frontend adapters under `frontends/`, and the HeroUI stack under `frontends/heroui/`.

## Python Style

### Formatting and density

- Prefer compact, direct Python over layered abstractions. `CONTRIBUTING.md` explicitly calls for self-documenting code, compact visual style, small change radius, minimal comments, and no blanket try/catch.
- Existing core files use dense one-line guards and assignments where the operation is obvious:
  - `agent_loop.py` uses `if event_sink is None: return`, `turn += 1; _emit_event(...)`, and small helpers such as `_tool_kind`, `_clean_content`, and `_compact_tool_args`.
  - `agentmain.py` initializes runtime state in compact assignments such as `self.history = []; self.handler = None` and uses concise queue-processing branches.
  - `ga.py` and `llmcore.py` keep many simple transformations inline to reduce scaffolding.
- Keep comments sparse and local. Comments in `agentmain.py`, `frontends/heroui/bridge.py`, and `frontends/heroui/bridge_core/routes.py` explain safety boundaries or compatibility decisions, not ordinary control flow.
- Use UTF-8 text and Chinese user-visible strings where the existing module already does so. Examples: `agent_loop.py` emits `未知工具`; `frontends/heroui/bridge_core/routes.py` returns Chinese/English bridge data; `tests/test_long_run_context.py` asserts Chinese long-run prompts.

### Type hints and dataclasses

- Use type hints for boundary objects and newer modules. `frontends/heroui/session_store.py`, `frontends/heroui/agent_state.py`, `frontends/heroui/bridge_core/session.py`, and `frontends/heroui/bridge_core/streaming.py` use `from __future__ import annotations`, `typing.Any`, and dataclasses.
- Dataclasses are used for small state/value records:
  - `agent_loop.py` defines `StepOutcome` with `data`, `next_prompt`, and `should_exit`.
  - `frontends/heroui/session_store.py` defines `StoredSession` for persisted rows.
  - `frontends/heroui/bridge_core/session.py` defines `Session` for in-memory bridge state.
  - Tests define lightweight fakes with dataclasses in `tests/test_agent_loop_events.py`.
- Do not introduce broad abstract base classes unless a real boundary exists. `agent_loop.py` has a small `BaseHandler` because tools dispatch dynamically through `do_<tool_name>` methods.

### Naming

- Python modules and functions use `snake_case`: `agent_runner_loop`, `try_call_generator`, `reload_mykeys`, `capture_agent_state`, `parse_positive_int`.
- Classes use `PascalCase`: `GenericAgent`, `GenericAgentHandler`, `AgentManager`, `SessionStore`, `EventStreamHub`, `WsHub`.
- Internal helpers use leading underscores when module-local: `_tool_result_status`, `_sanitize_leading_user_msg`, `_persist_session_and_message`, `_json_loads_strict`.
- Constants use `UPPER_SNAKE_CASE`: `NORMAL_RUNNER_MAX_TURNS`, `DEFAULT_HEROUI_DB_PATH`, `STATE_VERSION`, `TURN_POLL_INTERVAL_MS`.
- Runtime state fields are short but meaningful where hot-path code benefits from compactness: `sess`, `sid`, `turn_id`, `response_id`, `ga_turn`, `llm_no`.

## Compact Idioms to Preserve

- Generator-return values are part of the control flow. `agent_loop.py` uses `yield from try_call_generator(...)`, `StopIteration.value`, and the `StepOutcome` contract. Do not convert these paths to callback-heavy code without preserving generator return semantics.
- Tool outputs use dictionaries with stable status fields. `ga.py` returns `{"status": "success"|"error", ...}` from tools such as `code_run`, `web_scan`, `web_execute_js`, and `file_patch`.
- Use helper normalization at boundaries:
  - `agent_streaming.py` normalizes private protocol tags before UI streaming.
  - `frontends/heroui/agent_state.py` uses `_as_list` and `_as_dict` before restoring state.
  - `frontends/heroui/bridge_core/http_utils.py` uses `parse_positive_int` and `read_json` to keep route handlers small.
- Preserve current compatibility import pattern in bridge modules: `frontends/heroui/bridge.py` first tries package-relative imports, then adjusts `sys.path` and falls back to direct imports for script execution.

## Error Handling

### Core agent loop

- `agent_loop.py` treats errors as structured tool outcomes instead of relying only on exceptions:
  - `_tool_result_status` recognizes `file_read` string errors starting with `Error:`, dict statuses such as `error`/`failed`, and JSON strings returned by `web_execute_js`.
  - `_tool_result_output` returns stdout/content for successful tools and hides output when status is failed.
  - `_tool_result_error` extracts `msg`, `error`, `exception`, `stderr`, or `stdout` for failed tools.
- Unknown tool names are non-fatal turn outcomes. `BaseHandler.dispatch` yields `未知工具` and returns `StepOutcome(..., next_prompt="未知工具 ...", should_exit=False)`.
- Event sinks must never break the loop. `_emit_event` in `agent_loop.py` catches exceptions from `event_sink(event)` and drops them.

### Tool implementations

- Tools in `ga.py` return explicit error dictionaries for recoverable operational failures:
  - Unsupported code type in `code_run` returns `{"status": "error", "msg": ...}`.
  - Browser initialization failures in `web_scan` and `web_execute_js` return `{"status": "error", "msg": format_error(e)}`.
  - `file_patch` validates existence, empty old content, zero matches, and multiple matches with specific `msg` values.
- `format_error` in `ga.py` formats exception class, message, filename, line number, function name, and source line. Use it for user-visible tool errors where location matters.
- Avoid blanket catch blocks around critical initialization. Existing broad `except` blocks are used for optional integrations or fallback behavior, e.g. plugin discovery in `agentmain.py` and optional driver/browser paths in `ga.py`.

### HeroUI bridge

- `frontends/heroui/bridge.py` raises `aiohttp.web` HTTP exceptions at API boundaries: `HTTPBadRequest`, `HTTPNotFound`, and `HTTPConflict` with JSON bodies.
- Session state transitions are explicit: `idle`, `running`, `error`, `cancelled`. `AgentManager.run_agent_turn` sets `sess.last_error`, emits terminal events, persists state, and records an error message on exceptions.
- `frontends/heroui/bridge_core/http_utils.py` intentionally treats malformed JSON bodies as `{}` via `read_json`; route handlers validate required fields after parsing.
- `frontends/heroui/session_store.py` returns `None` for corrupt strict agent-state JSON so the bridge can fall back to message-derived state.

## State and Concurrency Patterns

### Core GenericAgent runtime

- `agentmain.py` uses a background worker thread plus `queue.Queue` for task submission:
  - `GenericAgent.put_task` creates a per-task display queue and enqueues `{query, source, images, output}`.
  - `GenericAgent.run` consumes tasks serially from `self.task_queue`, updates `self.is_running`, and publishes `next`/`done` dictionaries to the display queue.
  - `GenericAgent.abort` sets `self.stop_sig` and appends to `handler.code_stop_signal` for cooperative cancellation.
- `GenericAgent.lock` exists but `GenericAgent.run` mostly relies on single consumer serialization. Add shared state carefully and prefer queue ownership over ad-hoc cross-thread mutation.
- Streaming from `agent_runner_loop` is generator-based. Consumers should handle both text chunks and dictionaries such as `{turn: ...}` when `yield_info=True`.

### HeroUI bridge runtime

- `frontends/heroui/bridge.py` uses `threading.RLock` around shared `AgentManager.sessions`, session mutation, and persistence sequencing.
- Each submitted turn starts a daemon worker thread: `threading.Thread(target=self.run_agent_turn, ..., name=f"Turn-{sid}")`.
- Each bridge-backed `GenericAgent` also runs its own daemon agent thread named `GA-{sess.id}` in `make_agent`.
- `frontends/heroui/bridge_core/streaming.py` bridges threads to asyncio with `asyncio.run_coroutine_threadsafe` for websocket and SSE event publication.
- `EventStreamHub` subscribers are bounded `asyncio.Queue(maxsize=1000)`; if a queue is full, the oldest item is dropped before enqueueing the next event. Preserve this backpressure behavior for live streaming.
- `deleted_session_ids` in `frontends/heroui/bridge.py` is a safety guard: persistence helpers no-op for deleted sessions to prevent stale worker writes from resurrecting deleted sessions.

### Persistence state

- SQLite access is per-operation and context-managed in `frontends/heroui/session_store.py`; `connect()` sets `row_factory` and `PRAGMA foreign_keys = ON` each time.
- Persist sessions, messages, events, and agent state through `SessionStore` methods instead of direct SQL outside bridge/store internals.
- Agent continuation state is a bridge-owned artifact: `frontends/heroui/agent_state.py` captures `ga_history`, backend history, handler `working`, and `llm_no`.

## Import and Configuration Conventions

### Python imports

- Older core modules use compact grouped imports (`import os, sys, threading, queue, time, json, re, random, locale` in `agentmain.py`; `import os, json, re, time, requests, sys, threading, urllib3, base64, importlib, uuid` in `llmcore.py`). Match the local file style when editing existing modules.
- Newer bridge modules use one import per line with `from __future__ import annotations`; follow this pattern for new files under `frontends/heroui/bridge_core/` and `frontends/heroui/session_store.py`.
- Root imports depend on `sys.path` adjustments instead of packaged installation in several entry points. `agentmain.py`, `ga.py`, and `frontends/heroui/bridge.py` add the repo root or bridge directory to `sys.path` for direct script execution.
- Optional plugin/frontends should fail soft. `agentmain.py` suppresses plugin discovery failures; `frontends/heroui/bridge.py` supports both package and direct-script imports.

### Configuration

- Python project metadata is in `pyproject.toml`; no pytest/lint/formatter configuration file was detected in the repository root.
- Runtime language defaults are environment-driven. `agentmain.py` sets `GA_LANG` based on locale if not already set.
- HeroUI bridge configuration uses environment variables in `frontends/heroui/bridge.py` and `frontends/heroui/vite.config.ts`:
  - `HEROUI_BRIDGE_DB` selects the SQLite database path.
  - `HEROUI_BRIDGE_PORT` selects the bridge port.
  - `GA_HEROUI_API_TARGET` configures the Vite proxy target.
  - `VITE_GA_HEROUI_API_TARGET` configures frontend fetch base URL.
- Do not read or embed secret values from `mykey.py`, `mykey.json`, `.env`, `.npmrc`, or credential files. The map intentionally inspects templates/config shape only.

## Logging Style

- Logging is primarily `print`, not the Python `logging` module.
- `llmcore.py` replaces `print` with `safeprint` to suppress `OSError` during stream output, then uses tagged messages such as `[Info]`, `[Debug]`, `[Cut]`, `[Output]`, `[SSE]`, and `[WARN]`.
- `ga.py` prints command output directly from `code_run` while also collecting stdout for structured return values.
- `agentmain.py` prints abort/backend errors and writes task-mode stdout/stderr logs under `temp/<task>/` when running background task mode.
- `frontends/heroui/bridge.py` prints tracebacks to `stderr` for worker exceptions and suppresses aiohttp access logging by passing `print=None` to `web.run_app`.
- Prefer stable bracketed prefixes (`[Info]`, `[WARN]`, `[Debug]`) for new diagnostic prints so tests and UIs can filter predictably.

## Frontend Conventions

### TypeScript/React style

- The HeroUI frontend under `frontends/heroui/src/` is strict TypeScript (`frontends/heroui/tsconfig.json` has `strict: true`, `noEmit: true`, `jsx: react-jsx`).
- Imports use double quotes and explicit relative modules: `./api`, `./state`, `./types`, and HeroUI imports from `@heroui/react`.
- Data transformation belongs in pure helper modules:
  - `frontends/heroui/src/state.ts` owns turn reducers and thread/round construction.
  - `frontends/heroui/src/api.ts` owns HTTP/SSE/polling adaptation and backend-to-frontend mapping.
  - `frontends/heroui/src/ga_output_parser.ts`, `tool_details.ts`, and `sop_prompt.ts` own isolated parsing/formatting logic.
- `App.tsx` owns UI orchestration, local UI state, EventSource lifecycle, and component composition. Keep complex reducers out of components when possible.
- React state updates should be immutable. `frontends/heroui/src/state.ts` returns new arrays/objects with spread syntax, `map`, and helper merges instead of mutating existing state.

### Frontend async/error patterns

- API methods in `frontends/heroui/src/api.ts` use `fetch` plus `readJson<T>`; callers receive typed records rather than raw JSON.
- `subscribeTurn` prefers `EventSource`, closes on terminal events, and falls back to polling only when SSE fails before data arrives.
- Frontend errors are normalized for display. `App.tsx` has `readError(error: unknown): string` returning `error.message` or a Chinese fallback.
- Close EventSource instances through `closeActiveSource(source)` and cleanup effects rather than leaking subscriptions across sessions.

## Module Design and Exports

- Python modules mostly export functions/classes directly; there are few barrel/re-export modules. Keep public boundaries obvious by module path.
- HeroUI TypeScript modules export named functions/types. Tests import specific functions from `frontends/heroui/src/state.ts`, `tool_details.ts`, `sop_prompt.ts`, and `api.ts`.
- Keep route handlers thin. `frontends/heroui/bridge_core/routes.py` parses requests and delegates behavior to `AgentManager` in `frontends/heroui/bridge.py`.
- Keep persistence isolated. New SQLite schema or persistence behavior should be added in `frontends/heroui/session_store.py`, then used by `frontends/heroui/bridge.py`.

## Practical Guidance for Changes

- For agent-loop behavior, edit `agent_loop.py` and add focused tests in `tests/test_agent_loop_events.py` or `tests/test_agent_streaming.py`.
- For core tool behavior, edit `ga.py` and test returned dictionaries/status handling rather than only console text.
- For GenericAgent queue/thread behavior, edit `agentmain.py` and test with fake clients/handlers rather than real LLM calls.
- For HeroUI bridge API/session behavior, edit `frontends/heroui/bridge.py`, `frontends/heroui/bridge_core/*`, or `frontends/heroui/session_store.py`; cover with `tests/test_heroui_session_store.py`, `tests/test_heroui_agent_state.py`, or frontend contract tests in `frontends/heroui/src/*.test.mjs`.
- For frontend event/state rendering, put pure logic in `frontends/heroui/src/state.ts` or `frontends/heroui/src/api.ts` and test with `node:test` files under `frontends/heroui/src/`.

## Evidence / Examples Inspected

- Project/config: `pyproject.toml`, `frontends/heroui/package.json`, `frontends/heroui/tsconfig.json`, `frontends/heroui/vite.config.ts`, `frontends/heroui/pnpm-lock.yaml`, `CONTRIBUTING.md`, `README.md`.
- Core Python: `agentmain.py`, `agent_loop.py`, `agent_streaming.py`, `ga.py`, `llmcore.py`.
- HeroUI bridge Python: `frontends/heroui/bridge.py`, `frontends/heroui/session_store.py`, `frontends/heroui/agent_state.py`, `frontends/heroui/bridge_core/routes.py`, `frontends/heroui/bridge_core/session.py`, `frontends/heroui/bridge_core/streaming.py`, `frontends/heroui/bridge_core/http_utils.py`.
- HeroUI frontend: `frontends/heroui/src/App.tsx`, `frontends/heroui/src/api.ts`, `frontends/heroui/src/state.ts`, `frontends/heroui/src/tool_details.ts`, `frontends/heroui/src/sop_prompt.ts`, `frontends/heroui/src/ga_output_parser.ts`.
- Tests: `tests/test_agent_loop_events.py`, `tests/test_agent_streaming.py`, `tests/test_llmcore_fast_ask.py`, `tests/test_long_run_context.py`, `tests/test_heroui_agent_state.py`, `tests/test_heroui_session_store.py`, `tests/test_simple_http_server.py`, `tests/test_goal_mode.py`, `frontends/heroui/src/state.test.mjs`, `frontends/heroui/src/api_stream.test.mjs`, `frontends/heroui/src/ga_bridge_contract.test.mjs`, `frontends/heroui/src/ui_contract.test.mjs`, `frontends/heroui/src/ga_output_parser.test.mjs`, `frontends/heroui/src/tool_details.test.mjs`, `frontends/heroui/src/sop_prompt.test.mjs`.

## Gaps / Unknowns

- No root formatter configuration (`black`, `ruff`, `prettier`, `biome`, or ESLint config) was detected from inspected root files; style is convention-by-example.
- No root pytest configuration file was detected. Existing `tests/__pycache__` indicates pytest has been used, but command policy is not encoded in config.
- No coverage threshold or coverage tool configuration was detected.
- No project-wide frontend lint command was detected in `frontends/heroui/package.json`; `build` performs `tsc --noEmit` and Vite build, while `test` runs selected `node:test` files through `tsx`.
- Some older adapters under `frontends/` are large and predate the typed bridge style; this map samples conventions from core files and the actively tested HeroUI path rather than every adapter implementation.
