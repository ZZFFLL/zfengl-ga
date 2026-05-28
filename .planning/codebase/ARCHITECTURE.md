---
title: Architecture
focus: arch
generated_at: 2026-05-28
last_mapped_commit: 0741fd20140a70bbe4317edcf72b228e4c279422
---

# Architecture

## System Overview

GenericAgent is a Python autonomous-agent runtime with a centralized execution loop and multiple adapters around it.

```text
User / Scheduler / Bot / UI
  │
  ├─ CLI and runtime modes: `agentmain.py`, `ga_cli/cli.py`, `launch.pyw`
  ├─ Python frontends: `frontends/stapp.py`, `frontends/tui_v3.py`, `frontends/tgapp.py`, `frontends/fsapp.py`, ...
  ├─ ACP stdio bridge: `frontends/genericagent_acp_bridge.py`
  └─ HeroUI stack: `frontends/heroui/bridge.py` + `frontends/heroui/src/*`
        │
        ▼
`agentmain.GenericAgent`
  - task queue, selected LLM client, runtime flags, process-local history
  - daemon `run()` loop receiving tasks from adapters
        │
        ▼
`agent_loop.agent_runner_loop`
  - turn loop, model streaming, structured event emission, tool dispatch
        │
        ├─ LLM abstraction: `llmcore.py`
        │   ├─ `ToolClient` text-protocol tool calls
        │   ├─ `NativeToolClient` native tool-use APIs
        │   └─ `MixinSession` same-family fallback sessions
        │
        └─ Tool/handler layer: `ga.GenericAgentHandler`
            ├─ maps tool names to `do_<tool>` methods
            ├─ owns short-term working memory and turn-end control prompts
            └─ implements file, code, browser, human-interrupt, and memory tools
```

The default persistence model is process memory plus files in `temp/` and `memory/`. The HeroUI bridge adds SQLite persistence via `frontends/heroui/session_store.py`, defaulting to `frontends/heroui/.data/sessions.sqlite3` from `frontends/heroui/bridge_core/session.py`.

## Primary Components

| Component | Responsibility | Files |
|---|---|---|
| Agent orchestration | Queue tasks, select model, build system prompt, create handlers, drain loop output into frontend display queues. | `agentmain.py` |
| Agent loop | Turn sequencing, model stream filtering, tool dispatch, tool-result normalization, lifecycle hooks, structured events. | `agent_loop.py`, `agent_streaming.py` |
| LLM abstraction | Provider request construction, SSE/JSON parsing, native/text tool-call adaptation, fallback sessions, prompt/response logging. | `llmcore.py` |
| Tool implementation | Model-callable tools and working-memory/plan-mode control. | `ga.py`, `assets/tools_schema.json`, `assets/tools_schema_cn.json` |
| Memory system | Global memory prompt injection, SOP files, file access stats, long-term memory update workflow. | `ga.py`, `memory/*.md`, `assets/insight_fixed_structure*.txt` |
| Frontend adapters | Translate platform events into `GenericAgent.put_task()` calls and render display queue output. | `frontends/*.py`, `launch.pyw`, `ga_cli/cli.py` |
| HeroUI bridge | HTTP command API, SSE stream, WS notifications, persisted sessions/state, React contract mapping. | `frontends/heroui/bridge.py`, `frontends/heroui/bridge_core/*.py`, `frontends/heroui/src/*.ts`, `frontends/heroui/src/*.tsx` |
| Plugin hooks | In-process extension points and Langfuse tracing plugin. | `plugins/hooks.py`, `plugins/langfuse_tracing.py` |
| Reflect modes | Polling scripts that generate agent tasks without direct UI input. | `agentmain.py`, `reflect/goal_mode.py`, `reflect/scheduler.py` |

## Primary Control Flow

### Interactive / Adapter Request Path

1. A frontend or bridge creates `agentmain.GenericAgent`, selects an LLM if needed, sets flags such as `verbose`, `inc_out`, or `structured_events`, and starts `agent.run()` in a daemon thread (`agentmain.py:43-105`, `frontends/stapp.py`, `frontends/tgapp.py`, `frontends/heroui/bridge.py:83-983`).
2. The frontend submits work with `GenericAgent.put_task(query, source, images)` and receives a display queue (`agentmain.py:88-91`).
3. `GenericAgent.run()` pulls a task, handles slash commands, builds the system prompt from `assets/sys_prompt*.txt` plus `ga.get_global_memory()`, creates `ga.GenericAgentHandler`, and calls `agent_loop.agent_runner_loop()` (`agentmain.py:100-178`).
4. `agent_runner_loop()` calls the active LLM client with `client.chat(messages, tools_schema)`, streams chunks, filters private protocol tags with `agent_streaming.ModelDisplayStreamFilter`, and emits `llm.visible_delta` events when `event_sink` is set (`agent_loop.py:131-211`).
5. The loop turns native/text model tool calls into records with `tool_name`, `args`, and `id`; no-tool responses are converted into the synthetic `no_tool` dispatch (`agent_loop.py:212-219`).
6. `BaseHandler.dispatch()` calls `GenericAgentHandler.do_<tool_name>()`, wrapping generator and non-generator tools into `StepOutcome` (`agent_loop.py:13-30`, `ga.py:213-648`).
7. Tool results are appended to the next turn as `tool_results`; `GenericAgentHandler.turn_end_callback()` records a short summary and injects review/checkpoint/plan/memory prompts when thresholds or task files require it (`agent_loop.py:296-311`, `ga.py:597-648`).
8. Completion emits `agent.final` and `agent.done`; `GenericAgent.run()` writes incremental `next` and final `done` messages back to the display queue (`agent_loop.py:281-316`, `agentmain.py:165-178`).

### One-Shot Task Mode

`agentmain.py --task IODIR` supports file-based task execution. Without `--nobg`, it respawns itself detached and writes logs under `temp/<task>/stdout.log` and `temp/<task>/stderr.log`. With `--nobg`, it reads `temp/<task>/input.txt`, writes `output*.txt`, consumes `reply.txt` for follow-up rounds, restores `_history.json` if present, and honors `_stop` (`agentmain.py:207-263`).

### Reflect Runtime Mode

`agentmain.py --reflect SCRIPT` loads a module with optional `init(args)`, repeated `check()`, optional `on_done(result)`, `INTERVAL`, and `ONCE` (`agentmain.py:264-286`). `reflect/goal_mode.py` uses a JSON goal state file and emits continuation prompts. `reflect/scheduler.py` uses a port lock, JSON task files under `sche_tasks/`, and repeat parsing for once/daily/weekday/weekly/monthly/every-N tasks.

## Agent Loop

`agent_loop.py` is the execution kernel. Keep turn orchestration here; frontends should submit tasks and render queue/events rather than reimplement loop behavior.

Key responsibilities:

- Build the initial system/user message pair and per-turn tool-result message (`agent_loop.py:134-137`, `agent_loop.py:309-311`).
- Trigger lifecycle hooks: `agent_before`, `turn_before`, `llm_before`, `llm_after`, `turn_after`, `agent_after` (`agent_loop.py:139-151`, `agent_loop.py:199-200`, `agent_loop.py:309-314`).
- Stream visible deltas only; `<thinking>`, `<summary>`, `<tool_use>`, `<tool_call>`, and `<file_content>` are filtered by `agent_streaming.ModelDisplayStreamFilter` (`agent_loop.py:154-197`, `agent_streaming.py`).
- Normalize tool status/output/error through `_tool_result_status()`, `_tool_result_output()`, and `_tool_result_error()` for downstream UI cards (`agent_loop.py:52-98`, `agent_loop.py:270-280`).
- Emit optional structured raw events through `_emit_event()`; sink failures are swallowed so UI transport failures do not stop tool execution (`agent_loop.py:110-117`).
- Stop on `StepOutcome.should_exit`, empty `next_prompt`, exhausted done hooks, or `max_turns` (`agent_loop.py:281-316`).

Raw event names from the loop include `turn.start`, `llm.start`, `llm.visible_delta`, `llm.end`, `tool.start`, `tool.delta`, `tool.end`, `agent.final`, `turn.end`, and `agent.done`.

## LLM Abstraction

`llmcore.py` exposes a loop-facing `chat(messages, tools)` protocol while supporting multiple provider/session styles.

### Sessions

- `BaseSession` owns API key/base/model/config, thread-safe `history`, context trimming, and streaming/non-streaming `ask()` (`llmcore.py:518-584`).
- `ClaudeSession` calls Anthropic-style `/messages`, applies prompt caching, and parses Claude SSE/JSON (`llmcore.py:596-619`).
- `LLMSession` calls OpenAI-compatible chat-completions/responses through `_openai_stream()` and converts messages with `_msgs_claude2oai()` (`llmcore.py:621-623`).
- `NativeClaudeSession` and `NativeOAISession` preserve native tool-use content blocks and return `MockResponse` with `thinking`, `content`, and `tool_calls` (`llmcore.py:675-817`).
- `MixinSession` composes same-family sessions for fallback and spring-back; it broadcasts mutable attributes such as `system`, `tools`, `temperature`, `max_tokens`, and `history` (`llmcore.py:916-975`).

### Clients

- `ToolClient` converts `assets/tools_schema*.json` into text-protocol instructions, logs prompts/responses to `temp/model_responses/`, and parses `<tool_use>` XML/JSON/text fallback calls into `MockToolCall` (`llmcore.py:837-913`, `llmcore.py:879-893`).
- `NativeToolClient` sends native tool schemas, tracks pending tool IDs, converts tool results back into content blocks, and installs the always-on summary/thinking prompt (`llmcore.py:997-1057`).
- `resolve_session()` and `resolve_client()` select clients from `mykey` configuration names (`llmcore.py:1059-1067`).
- `GenericAgent.load_llm_sessions()` loads `mykey` entries whose names include `api`, `config`, or `cookie`, then wraps them as `ToolClient`, `NativeToolClient`, or `MixinSession` (`agentmain.py:59-82`).

## Handler and Tool Dispatch

`agent_loop.BaseHandler.dispatch()` maps tool names to `do_<name>` methods and injects `_index`/`_tool_num` into args (`agent_loop.py:18-30`). `ga.GenericAgentHandler` implements the current tool set from `assets/tools_schema.json`:

| Tool | Handler | Architectural notes |
|---|---|---|
| `code_run` | `GenericAgentHandler.do_code_run()` | Runs Python/PowerShell through `ga.code_run()` or in-process `inline_eval`; respects `code_stop_signal`. |
| `file_read` | `GenericAgentHandler.do_file_read()` | Reads relative to handler `cwd`; appends memory/SOP tips when reading memory paths. |
| `file_patch` | `GenericAgentHandler.do_file_patch()` | Unique exact replacement only; expands `{{file:path:start:end}}` references before write. |
| `file_write` | `GenericAgentHandler.do_file_write()` | Whole-file create/overwrite/append/prepend; content normally comes from `<file_content>` or a code fence. |
| `web_scan` | `GenericAgentHandler.do_web_scan()` | Uses browser helpers in `ga.py`, `TMWebDriver.py`, and `simphtml.py`. |
| `web_execute_js` | `GenericAgentHandler.do_web_execute_js()` | Executes JS through the browser driver; can save long JS return values to files. |
| `update_working_checkpoint` | `GenericAgentHandler.do_update_working_checkpoint()` | Updates `handler.working` with `key_info`, `related_sop`, and reset `passed_sessions`. |
| `ask_user` | `GenericAgentHandler.do_ask_user()` | Returns a human-intervention payload and exits the current loop with `should_exit=True`. |
| `start_long_term_update` | `GenericAgentHandler.do_start_long_term_update()` | Loads `memory/memory_management_sop.md` and asks the model to distill verified long-term memory. |

`GenericAgentHandler.do_no_tool()` is not in the schema; the loop invokes it when the model does not call a tool. It validates empty/incomplete responses, intercepts unverified plan-mode completion claims, handles large-code-block/no-tool ambiguity, and allows final answers (`ga.py:405-470`).

## Memory System

There are three memory layers in the runtime:

1. **Process-local task history**: `GenericAgent.history` stores user summaries, and `GenericAgentHandler.history_info` stores `[Agent] <summary>` lines for the active task (`agentmain.py:43-178`, `ga.py:597-648`).
2. **Short-term working memory**: `GenericAgentHandler.working` stores `key_info`, `related_sop`, plan-mode state, and pass counters. It is injected into `_get_anchor_prompt()` and can be updated by `update_working_checkpoint` (`ga.py:387-398`, `ga.py:526-548`).
3. **Long-term memory/SOP files**: `get_global_memory()` reads `memory/global_mem_insight.txt` and `assets/insight_fixed_structure*.txt` into the system prompt; `start_long_term_update` loads `memory/memory_management_sop.md` (`ga.py:648-660`, `ga.py:471-489`).

HeroUI persists continuation state in SQLite table `agent_state` through `frontends/heroui/session_store.py` and maps it to/from live agents through `frontends/heroui/agent_state.py`. Persisted state includes `ga_history`, backend `history`, handler `working`, `llm_no`, and `state_version`.

## Event Streaming and UI State

### Core Raw Events

When `GenericAgent.structured_events` is true, `GenericAgent.run()` passes an `event_sink` that forwards raw loop events as `{'event': event, 'source': source}` display-queue items (`agentmain.py:141-150`). HeroUI enables this in `AgentManager.make_agent()` (`frontends/heroui/bridge.py:244-259`).

### HeroUI Event Pipeline

1. `AgentManager.run_agent_turn()` drains the agent display queue, identifies structured raw events, and passes each raw event through `convert_agent_event()` (`frontends/heroui/bridge.py:640-777`).
2. `frontends/heroui/bridge_core/events.py` maps raw loop events into UI contract events such as `answer.delta`, `answer.final`, `timeline.step`, `turn.done`, and `turn.error`.
3. `AgentManager.add_event()` assigns monotonically increasing `seq`, stores the event in memory and SQLite, and publishes through `EventStreamHub` (`frontends/heroui/bridge.py:159-181`).
4. `BridgeRoutes.events_handler()` serves replay plus live events over SSE with `Last-Event-ID`/`after_event` cursor support (`frontends/heroui/bridge_core/routes.py:215-288`).
5. The React client subscribes via `frontends/heroui/src/api.ts:264-331`; if `EventSource` is unavailable, it uses polling.
6. `frontends/heroui/src/state.ts` applies events into `TurnState`, timeline steps, artifacts, and final assistant messages.

`WsHub` in `frontends/heroui/bridge_core/streaming.py` is used for lightweight session-state notifications (`bridge-ready`, `session-state`). Command/data traffic stays on HTTP/SSE via `BridgeRoutes`.

### Non-HeroUI Display Queues

Most Python frontends consume display queue dictionaries directly:

- `{'next': text, 'turn': n, 'outputs': [...]}` for incremental output.
- `{'done': text, 'turn': n, 'outputs': [...]}` for final output.
- Some adapters install `_turn_end_hooks` to detect `ask_user` and render platform-native menus, as seen in `frontends/tgapp.py` and `frontends/fsapp.py`.

## Frontend Boundaries

### Python Adapters

Adapters under `frontends/` should treat `GenericAgent` as the boundary. They create or reuse an agent, call `put_task()`, and render display queue output.

- `frontends/chatapp_common.py` contains shared bot/chat helpers: reply cleanup, file marker handling, restore helpers, single-instance checks, runtime validation, and `AgentChatMixin`.
- `frontends/stapp.py` is the Streamlit UI; it caches one `GeneraticAgent`, stores UI messages in `st.session_state`, and drains the display queue in `agent_backend_stream()` / `render_main_stream()`.
- `frontends/tui_v3.py` is a large self-contained terminal UI. Its `AgentBridge` wraps one `GeneraticAgent` per session and converts display queue records into typed TUI events.
- `frontends/tgapp.py`, `frontends/fsapp.py`, `frontends/wechatapp.py`, `frontends/wecomapp.py`, `frontends/dingtalkapp.py`, and `frontends/qqapp.py` adapt platform messages, auth/allow-lists, media/file transfer, and streaming constraints to the same agent boundary.
- `frontends/genericagent_acp_bridge.py` exposes an ACP-compatible JSON-RPC stdio server. It creates one `GeneraticAgent` per ACP session and streams `agent_message_chunk` updates from display queue deltas.

### HeroUI Full-Stack Boundary

HeroUI is split into three layers:

- **Manager/runtime**: `frontends/heroui/bridge.py` owns `AgentManager`, session lifecycle, `GenericAgent` construction, per-turn threads, replay/cancel/title regeneration, and continuation-state persistence.
- **HTTP/SSE/WS routes**: `frontends/heroui/bridge_core/routes.py` owns request parsing, CORS, route registration, SOP editing/listing under `memory/`, SSE cursor replay, and static file serving.
- **React client**: `frontends/heroui/src/api.ts`, `frontends/heroui/src/state.ts`, `frontends/heroui/src/App.tsx`, and `frontends/heroui/src/components/*.tsx` own API calls, event reduction, and presentation.

Keep new bridge business logic in `frontends/heroui/bridge.py` or focused modules under `frontends/heroui/bridge_core/`; keep React-only event/state mapping in `frontends/heroui/src/*`.

## Plugin System

`plugins/hooks.py` is a small global callback registry:

- `register(event)` decorates callbacks.
- `trigger(event, ctx)` runs callbacks and lets a callback replace the context by returning a dict.
- `discover_and_load()` imports every non-underscore `*.py` in `plugins/`.

`agentmain.py` calls `plugins.hooks.discover_and_load()` during import (`agentmain.py:12-14`). `agent_loop.py` triggers agent/turn/LLM lifecycle hooks, and `BaseHandler.dispatch()` triggers `tool_before` / `tool_after` (`agent_loop.py:18-30`, `agent_loop.py:139-314`). `plugins/langfuse_tracing.py` self-activates when `langfuse_config` exists in `mykey` and registers agent, LLM, and tool spans; it also wraps SSE parsers for usage tracking.

## Runtime Modes

| Mode | Entry point | State/control path |
|---|---|---|
| Direct CLI chat | `python agentmain.py` | Starts `GenericAgent.run()` thread, reads stdin, prints display queue output. |
| File task | `python agentmain.py --task IODIR` | Uses `temp/<task>/input.txt`, `output*.txt`, `reply.txt`, `_history.json`, `_stop`. |
| Reflect polling | `python agentmain.py --reflect reflect/*.py` | Reflect module `check()` generates tasks; `on_done()` can update reflect state. |
| Package command | `ga` / `ga_cli/cli.py` | Dispatches commands to launch frontends/tools. |
| Desktop wrapper | `launch.pyw` | Starts Streamlit, optional bots/scheduler, idle monitor, and `pywebview`. |
| Streamlit UI | `frontends/stapp.py` | One cached `GeneraticAgent`; UI session state in Streamlit. |
| TUI | `frontends/tui_v3.py` | Terminal session bridge with typed queue events and local settings in `temp/tui_v3_settings.json`. |
| Bots | `frontends/tgapp.py`, `frontends/fsapp.py`, etc. | Platform event handlers call `put_task()` and stream back platform-specific messages/cards. |
| ACP bridge | `frontends/genericagent_acp_bridge.py` | JSON-RPC over stdio; one agent per ACP session. |
| HeroUI | `frontends/heroui/start.cmd`, `frontends/heroui/bridge.py`, `frontends/heroui/src/*` | Vite React frontend + aiohttp bridge + SQLite session store. |

## Architectural Constraints

- **Threading:** `GenericAgent.run()` is a blocking loop intended to run on a background thread. HeroUI creates a daemon thread per live session turn and an agent runner thread per session. Shared mutable state is protected inconsistently: HeroUI uses `threading.RLock` in `AgentManager`, while `GenericAgent` uses a task queue and ad hoc flags (`agentmain.py`, `frontends/heroui/bridge.py`).
- **Global state:** `llmcore.py` lazily loads `mykey`; `ga.py` has global browser `driver`; `plugins/hooks.py` has module-level `_registry`; `agentmain.py` initializes memory/template files at import time.
- **Working directory:** Core tools resolve paths relative to handler `cwd`, usually `temp/`. HeroUI temporarily changes process cwd while constructing agents in `AgentManager.make_agent()` and restores it afterward (`frontends/heroui/bridge.py:244-259`).
- **Tool schema:** Tool names in `assets/tools_schema*.json` must match `GenericAgentHandler.do_<name>` methods or dispatch returns an unknown-tool prompt (`agent_loop.py:18-30`).
- **Protocol tags:** Model-visible protocol tags are part of runtime behavior. Frontends must not display raw `<thinking>`, `<summary>`, `<tool_use>`, or `<file_content>` blocks without intentional rendering/filtering.
- **Secret files:** Configuration is loaded from `mykey.py` / `mykey.txt` style paths. Do not include secret values in codebase maps or UI logs.

## Where to Modify Behavior

- Change turn sequencing, event names, or tool-result normalization in `agent_loop.py`.
- Add a new model provider/session in `llmcore.py`, then wire selection through `resolve_session()` / `resolve_client()`.
- Add a model-callable tool by adding `GenericAgentHandler.do_<tool>()` in `ga.py` and schema entries in `assets/tools_schema.json` and `assets/tools_schema_cn.json`.
- Add lifecycle tracing/instrumentation by registering hooks in `plugins/*.py`; do not monkey-patch the loop unless hooks are insufficient.
- Add a normal Python frontend by using `GenericAgent.put_task()` and consuming `next`/`done` display queue records.
- Add HeroUI API endpoints in `frontends/heroui/bridge_core/routes.py`, business/session behavior in `frontends/heroui/bridge.py`, event mapping in `frontends/heroui/bridge_core/events.py`, and React state handling in `frontends/heroui/src/state.ts`.
- Add reflect/autonomous modes as modules under `reflect/` with `check()` and optional `init()` / `on_done()`.

## Evidence / Examples Inspected

Main files inspected for this map:

- `pyproject.toml`
- `README.md`
- `agentmain.py`
- `agent_loop.py`
- `agent_streaming.py`
- `llmcore.py`
- `ga.py`
- `assets/tools_schema.json`
- `plugins/hooks.py`
- `plugins/langfuse_tracing.py`
- `frontends/chatapp_common.py`
- `frontends/stapp.py`
- `frontends/tui_v3.py`
- `frontends/tgapp.py`
- `frontends/fsapp.py`
- `frontends/genericagent_acp_bridge.py`
- `frontends/heroui/bridge.py`
- `frontends/heroui/bridge_core/session.py`
- `frontends/heroui/bridge_core/routes.py`
- `frontends/heroui/bridge_core/streaming.py`
- `frontends/heroui/bridge_core/events.py`
- `frontends/heroui/session_store.py`
- `frontends/heroui/agent_state.py`
- `frontends/heroui/src/api.ts`
- `frontends/heroui/src/state.ts`
- `frontends/heroui/src/App.tsx`
- `frontends/heroui/package.json`
- `frontends/heroui/vite.config.ts`
- `frontends/heroui/start.cmd`
- `ga_cli/cli.py`
- `launch.pyw`
- `reflect/goal_mode.py`
- `reflect/scheduler.py`
- `tests/test_agent_loop_events.py`
- `tests/test_agent_streaming.py`
- `tests/test_heroui_agent_state.py`
- `tests/test_heroui_session_store.py`

## Gaps / Unknowns

- No project-local `.claude/skills/` or `.agents/skills/` directory was present during mapping, so no project skill architecture rules were incorporated.
- Secret/config files such as `mykey.py`, `mykey.txt`, and any environment files were intentionally not inspected; model profile and integration details are inferred only from code paths that load them.
- The exact behavior of every bot adapter under `frontends/` was not exhaustively mapped; the common boundary is evidenced through `frontends/chatapp_common.py`, `frontends/tgapp.py`, and `frontends/fsapp.py`.
- Generated/runtime directories such as `temp/`, `__pycache__/`, `.pytest_cache/`, `frontends/heroui/.vite/`, and HeroUI SQLite contents were not inspected as source architecture.
- `frontends/desktop/src-tauri/` was identified as a Tauri desktop packaging boundary, but Rust internals were not deeply inspected for this architecture map.
