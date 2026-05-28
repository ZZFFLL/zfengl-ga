---
title: Codebase Concerns
focus: concerns
generated_at: 2026-05-28
last_mapped_commit: 0741fd20140a70bbe4317edcf72b228e4c279422
---

# Codebase Concerns

**Analysis Date:** 2026-05-28

This document lists practical risk areas in severity order. Each concern includes concrete files to inspect before changing the area.

## Critical Severity

### Local HeroUI bridge exposes powerful unauthenticated controls

- **Issue:** The HeroUI bridge exposes prompt submission, config mutation, SOP editing, model switching, deletion, cancellation, and local path opening through HTTP routes without authentication. `frontends/heroui/bridge_core/http_utils.py` returns `Access-Control-Allow-Origin: "*"`, and `frontends/heroui/bridge_core/routes.py` registers mutating routes such as `POST /config`, `PUT /sops/{sop_id}`, `POST /session/{sid}/prompt`, `DELETE /session/{sid}`, and `POST /path/open`.
- **Files:** `frontends/heroui/bridge_core/http_utils.py`, `frontends/heroui/bridge_core/routes.py`, `frontends/heroui/bridge.py`, `frontends/heroui/src/api.ts`
- **Evidence:** `frontends/heroui/bridge.py` binds to `127.0.0.1` by default, but it also honors `BRIDGE_HOST`; a wider bind combined with wildcard CORS gives any browser origin access to bridge operations.
- **Impact:** A malicious local webpage or any page reachable from a browser on the host can drive agent prompts, mutate UI-visible configuration, overwrite existing SOP markdown files under `memory/`, open arbitrary local paths with the OS handler, and consume LLM budget.
- **Safe modification:** Add an explicit local auth token or origin-bound nonce before any bridge operation that mutates state or invokes the agent. Keep `127.0.0.1` as the default and reject non-loopback `BRIDGE_HOST` unless an operator explicitly enables remote mode.
- **Tests required:** Add route-level tests for missing token, wrong token, allowed token, OPTIONS behavior, and the `BRIDGE_HOST` remote-mode guard.

### Agent tool execution is intentionally powerful and not sandboxed

- **Issue:** `code_run`, `file_write`, `file_patch`, `file_read`, and `web_execute_js` operate on local files and processes. Path resolution uses `os.path.abspath(os.path.join(self.cwd, path))` without an allowlist, so `..` traversal or absolute-path-like inputs can escape the intended work area. `code_run` executes Python and shell commands through `subprocess.Popen`, and `inline_eval` calls `eval`/`exec` in-process.
- **Files:** `ga.py`, `agent_loop.py`, `assets/tools_schema.json`, `assets/tools_schema_cn.json`
- **Evidence:** `ga.py` implements `code_run` with `subprocess.Popen`, `do_code_run` with optional `inline_eval`, `do_file_write` with overwrite/append/prepend, `file_patch` with full-file read/write replacement, and `do_web_execute_js` with optional `save_to_file`.
- **Impact:** Prompt injection or a mistaken tool call can execute host commands, write or overwrite files outside `temp/`, read sensitive files, or persist browser-extracted data. This is acceptable only if the agent process is treated as fully trusted local automation.
- **Safe modification:** Preserve explicit power for trusted local use, but centralize path policy and execution policy behind one guard function. At minimum, add dry-run/confirmation gates for paths outside the repository or user-approved roots, and make every bypass explicit in one place.
- **Tests required:** Add unit tests around `_get_abs_path`/new path guard, absolute paths, `..` traversal, append/prepend/overwrite semantics, `save_to_file`, and command timeout/stop behavior.

### Secrets handling relies on local convention rather than strong protection

- **Issue:** LLM API keys are loaded from `mykey.py` or `mykey.json` by `llmcore.py`. `.gitignore` excludes `mykey.py`, `.env`, `auth.json`, logs, and generated `assets/tmwd_cdp_bridge/config.js`, but `llmcore.reload_mykeys()` catches all exceptions and returns the previous in-memory config. `memory/keychain.py` stores secrets in `~/ga_keychain.enc` with a username-derived XOR mask, not cryptographic encryption.
- **Files:** `llmcore.py`, `.gitignore`, `mykey_template_en.py`, `memory/keychain.py`, `frontends/heroui/bridge_core/routes.py`
- **Evidence:** `mykey_template_en.py` instructs users to copy the template to `mykey.py` and fill `apikey`; `llmcore.py` loads `mykey.py` via import/reload and builds provider headers with API keys; `memory/keychain.py` stores key material with `_xor` and prints a masking helper warning.
- **Impact:** Syntax/load errors in key config can silently leave stale credentials active. The keychain file protects against casual viewing but not local compromise. `/status`, `/config`, and `/ws` include `mykeyPath`, which leaks local path layout to bridge clients.
- **Safe modification:** Make config reload failures visible and fail closed for new sessions unless explicitly configured to keep the last good config. Do not expose `mykeyPath` over unauthenticated bridge endpoints. Label `memory/keychain.py` as obfuscation-only or switch to OS keychain storage.
- **Tests required:** Add tests for bad `mykey.py`, bad `mykey.json`, stale-config behavior, and bridge responses that omit sensitive local path metadata unless authorized.

## High Severity

### Broad exception handling hides data loss and stale state

- **Issue:** Broad `except Exception` and bare `except:` handlers are widespread, including silent `pass`, `continue`, and fallback return paths. A pattern scan found at least 35 broad-exception hits and at least 35 bare-exception hits before hitting the scan cap.
- **Files:** `agentmain.py`, `agent_loop.py`, `ga.py`, `llmcore.py`, `frontends/heroui/bridge.py`, `frontends/heroui/session_store.py`, `frontends/continue_cmd.py`, `frontends/tuiapp_v2.py`, `frontends/tui_v3.py`
- **Evidence:** `llmcore.reload_mykeys()` returns previous `mykeys` on any exception; `agentmain.py` suppresses plugin load failures and many model/session failures; `agent_loop._emit_event()` suppresses all event sink errors; `frontends/heroui/session_store.py` returns defaults or `None` on corrupt JSON; `ga.py` suppresses stream reader failures and many file-scan errors.
- **Impact:** Configuration errors, persistence corruption, event delivery failure, and tool execution bugs can be converted into plausible but stale behavior. Operators may not learn that the live agent is using older credentials, incomplete state, or missing events.
- **Safe modification:** Replace catch-all handling with typed exceptions in reliability-sensitive paths. When continuing is intentional, emit structured warnings into the same surface the user sees, not only stdout/stderr.
- **Tests required:** Add failure-path tests for config reload, event sink failure, corrupt persisted state, file write failure, and LLM stream interruption.

### Sync/threading boundaries share mutable state across agents and event loops

- **Issue:** The core agent is synchronous and thread-based. HeroUI wraps agent turns in per-session daemon threads while an aiohttp loop handles HTTP, SSE, and WebSocket traffic. Multiple shared objects cross these boundaries: `Session`, `sess.messages`, `sess.events`, `sess.partial`, `event_hub.subscribers`, `hub.websockets`, and monkey-patched `agentmain.GenericAgentHandler`.
- **Files:** `agentmain.py`, `frontends/heroui/bridge.py`, `frontends/heroui/bridge_core/session.py`, `frontends/heroui/bridge_core/streaming.py`, `agent_loop.py`
- **Evidence:** `frontends/heroui/bridge.py` starts `GA-{sid}`, `Turn-{sid}`, and `Replay-{sid}` daemon threads; `EventStreamHub.publish()` and `WsHub.emit()` call `asyncio.run_coroutine_threadsafe`; `AgentManager._install_handler_working_restore_hook()` mutates the imported `agentmain` module globally.
- **Impact:** Cancellation, deletion, replay, and prompt submission can race with persistence and event publishing. A session delete can mark `deleted_session_ids` while a turn thread still holds a `Session` reference. Module-level handler monkey-patching makes session-specific state restoration depend on global import state.
- **Safe modification:** Keep all `Session` mutation under `AgentManager.lock`; snapshot event payloads before publishing; avoid global monkey-patching by injecting a handler factory into each `GenericAgent` instance; add explicit lifecycle states for deleted/cancelling/completing.
- **Tests required:** Add tests for delete-while-running, cancel-while-persisting, replay-while-events-stream, multiple sessions running concurrently, and handler working-state isolation between two sessions.

### SQLite persistence is simple but has durability and concurrency limits

- **Issue:** Session state uses plain `sqlite3.connect()` per operation with `PRAGMA foreign_keys = ON`, but no explicit WAL mode, busy timeout, transaction isolation policy, schema migration table, backup strategy, or atomic checkpoint around multi-object in-memory state. JSON decode failures in `agent_state` return `None`, triggering message-derived fallback.
- **Files:** `frontends/heroui/session_store.py`, `frontends/heroui/bridge.py`, `frontends/heroui/bridge_core/session.py`, `tests/test_heroui_session_store.py`
- **Evidence:** `SessionStore.connect()` opens a new connection and only sets foreign keys; `load_all_sessions()` reads all sessions/messages/events into memory; `_json_loads_strict()` returns `None` for corrupt state; `AgentManager.persist_continuation_state()` captures live agent state and writes it after turns/cancellation.
- **Impact:** Under concurrent prompt/replay/delete/cancel operations, SQLite lock contention can surface as request failures. Corrupt `agent_state` silently drops to message reconstruction, which may lose working memory, backend history, and selected LLM details. Large event histories increase startup and memory cost because all events load at bridge startup.
- **Safe modification:** Configure WAL, `busy_timeout`, and a small migration/version table. Treat corrupt `agent_state` as a visible warning in the session. Page or cap event history during startup, and provide archival/compaction for old events.
- **Tests required:** Add concurrent writer tests, corrupt-state warning tests, schema migration tests, large-session load tests, and delete/replay transaction consistency tests.

### LLM provider retry/failover can mask partial failures

- **Issue:** Provider calls retry on selected HTTP/status and connection errors. Mixin failover detects strings starting with `!!!Error:` or `[Error:` and can switch providers, but partial streaming failures after some chunks are handled differently and can affect the next call rather than the current one.
- **Files:** `llmcore.py`, `agentmain.py`, `tests/test_llmcore_fast_ask.py`
- **Evidence:** `_stream_with_retry()` yields error text as model output after final failure; `MixinSession._raw_ask()` suppresses early error chunks until a healthy chunk appears, then yields streamed chunks; partial failures containing `[!!! 流异常中断` set `_cur_idx` for the next request. `agentmain.next_llm()` copies backend history to the next client.
- **Impact:** A user-visible answer can contain provider error strings or partial content. Failover may mix provider-specific message formats, tool-call behavior, context windows, and beta capabilities while sharing history. Debugging provider incidents is hard because successful failover hides the first failure unless logs are inspected.
- **Safe modification:** Emit structured provider-attempt events with provider name, status, retry count, and failover decision. Separate partial-stream failure handling from normal assistant content, and require compatibility validation for provider groups used by `MixinSession`.
- **Tests required:** Add tests for retryable HTTP, non-retryable HTTP, timeout, empty response, partial stream failure, failover after first provider failure, and history transfer across mixed provider types.

### Frontend/backend bridge event contract is complex and easy to desynchronize

- **Issue:** The HeroUI frontend reconstructs turns from HTTP snapshots, SSE events, EventSource fallback polling, legacy output parsing, and structured timeline events. The backend stores both message rows and event rows and sometimes synthesizes missing final/terminal events.
- **Files:** `frontends/heroui/bridge.py`, `frontends/heroui/bridge_core/events.py`, `frontends/heroui/bridge_core/routes.py`, `frontends/heroui/src/api.ts`, `frontends/heroui/src/state.ts`, `frontends/heroui/src/api_stream.test.mjs`
- **Evidence:** `frontends/heroui/src/api.ts` keeps `TURN_EVENT_CURSORS`, merges SSE and polling behavior, maps events into timelines, and preserves legacy output parsing. `frontends/heroui/bridge.py` has logic for `pending_terminal_event`, `add_final_event_if_missing`, `saw_structured_output_event`, and human intervention suppression.
- **Impact:** Small changes to event ordering, response IDs, turn IDs, or final-answer synthesis can create duplicate messages, missing final answers, stuck running steps, or replay cursor bugs.
- **Safe modification:** Treat the event schema as a versioned protocol. Add contract tests for backend-produced event sequences and frontend reducers together, not only separately.
- **Tests required:** Add end-to-end bridge protocol tests for SSE replay, polling fallback, replay turn truncation, human-intervention turns, cancellation, and backend restart with persisted events.

## Medium Severity

### Large files concentrate unrelated responsibilities

- **Issue:** Several files are large enough to hide bugs and make safe edits difficult: `frontends/tuiapp_v2.py` (~5793 lines), `frontends/tui_v3.py` (~5526 lines), `frontends/qtapp.py` (~2478 lines), `frontends/desktop/static/app.js` (~2113 lines), `assets/configure_mykey.py` (~1391 lines), `frontends/tgapp.py` (~1138 lines), `frontends/heroui/bridge.py` (~1083 lines), and `llmcore.py` (~1068 lines).
- **Files:** `frontends/tuiapp_v2.py`, `frontends/tui_v3.py`, `frontends/qtapp.py`, `frontends/desktop/static/app.js`, `assets/configure_mykey.py`, `frontends/tgapp.py`, `frontends/heroui/bridge.py`, `llmcore.py`, `ga.py`
- **Impact:** Cross-cutting edits require reading thousands of lines and understanding UI, state, transport, and business logic at once. Broad exception handling inside these large files increases the chance of hidden regressions.
- **Safe modification:** Split only along active change boundaries. For example, keep `frontends/heroui/bridge_core/*` as the pattern for bridge extraction; move route-only logic, persistence-only logic, and title-generation logic behind narrow interfaces before adding new behavior.
- **Tests required:** Before extracting a large file, pin its public behavior with focused tests around the exact functions being moved.

### UI and agent state durability depends on complete in-memory snapshots

- **Issue:** `AgentManager` stores sessions in memory and writes rows opportunistically. `load_all_sessions()` reloads all rows on bridge startup; `persist_continuation_state()` writes captured state at selected lifecycle points. Session titles are generated through the current LLM path.
- **Files:** `frontends/heroui/bridge.py`, `frontends/heroui/session_store.py`, `frontends/heroui/agent_state.py`, `tests/test_heroui_agent_state.py`
- **Impact:** Bridge crashes between user-message persistence and assistant-message persistence can leave a running turn restored as idle, with partial assistant content lost. Title generation failures or slow providers can affect session update timing.
- **Safe modification:** Persist explicit turn lifecycle rows (`accepted`, `running`, `done`, `error`) separately from derived UI state. Keep title generation out of the critical turn completion transaction.
- **Tests required:** Add restart/resume tests for accepted-before-run, run-before-final, final-before-agent-state, and title-generation failure.

### Configuration mutation has limited validation

- **Issue:** Bridge `/config` accepts arbitrary dictionaries and merges them into `manager.config`; `/model-profile` validates profile IDs only after creating a temporary `GenericAgent`; `/session.<attr>=...` in the CLI can set arbitrary backend attributes.
- **Files:** `frontends/heroui/bridge_core/routes.py`, `frontends/heroui/bridge.py`, `agentmain.py`
- **Impact:** Invalid config can persist in memory, affect UI assumptions, or change backend behavior without schema validation. CLI session overrides can create provider objects in states not exercised by tests.
- **Safe modification:** Define typed config schemas for bridge-visible settings and backend session overrides. Reject unknown fields unless an explicit expert/debug mode is enabled.
- **Tests required:** Add invalid-field, invalid-type, unsupported-profile, and session-override tests.

### File writes are non-atomic

- **Issue:** `ga.py` writes files directly for `file_write`, `file_patch`, memory access stats, task outputs, and JS save-to-file. `agentmain.py` writes task outputs and reflect logs directly. SQLite state uses transactions, but plain file writes do not use temp files, fsync, or atomic replace.
- **Files:** `ga.py`, `agentmain.py`, `frontends/heroui/bridge_core/routes.py`
- **Impact:** Process termination or disk errors can leave partial files. Concurrent agent/task writes to the same path can interleave at the application level.
- **Safe modification:** Use a shared atomic-write helper for overwrite operations where partial content is worse than a failed write. Keep append logs append-only, but make user-facing state files atomic.
- **Tests required:** Add tests for interrupted writes by injecting write failures and ensuring original content survives.

## Low Severity / Maintenance Pain Points

### Generated and runtime artifacts are present in the working tree

- **Issue:** The repository contains runtime/generated directories and files such as `.codegraph/`, `.pytest_cache/`, `__pycache__/`, `temp/`, and `frontends/heroui/.data/` may exist during local operation. `.gitignore` covers many of these, but mappers and tools must avoid treating them as source.
- **Files:** `.gitignore`, `temp/`, `.codegraph/`, `frontends/heroui/.data/`
- **Impact:** Accidental scans of runtime logs or databases can leak sensitive prompt content or consume large context. Mapping and code review should prefer tracked source files and avoid ignored runtime data.
- **Safe modification:** Keep runtime data ignored and add explicit reviewer/mapping rules to skip generated/runtime directories.

### Templates and docs mention provider names and placeholder keys

- **Issue:** `mykey_template_en.py` and `mykey_template.py` include placeholder key formats and provider setup examples. These are not secrets, but they are easy to confuse with real config.
- **Files:** `mykey_template_en.py`, `mykey_template.py`, `docs/installation.md`, `docs/GETTING_STARTED.md`
- **Impact:** Automated scanners and reviewers need to distinguish placeholders from real leaked keys. Do not copy real keys into templates or docs.
- **Safe modification:** Keep placeholders clearly marked and add secret-scanning checks that ignore known placeholders but fail on real token patterns.

## Test and CI Gaps

- **No repository-level CI detected:** `.github/` is not present. Python tests exist under `tests/`, and HeroUI frontend tests are configured in `frontends/heroui/package.json`, but no CI workflow file is detected.
- **Python test config is minimal:** `pyproject.toml` declares package metadata and dependencies but no pytest configuration, coverage thresholds, or lint/format tooling.
- **Coverage is concentrated:** Tests cover `agent_loop` events, HeroUI session store/state, streaming frontend behavior, and a `fast_ask` native Claude path. High-risk areas with little direct evidence include tool execution sandboxing, bridge auth/CORS, provider retry/failover matrix, concurrent session races, route security, and large legacy frontends.
- **Files:** `tests/`, `frontends/heroui/src/*.test.mjs`, `pyproject.toml`, `frontends/heroui/package.json`
- **Recommended gates:** Add CI jobs for targeted Python tests, HeroUI `pnpm test`, secret scanning, and focused route/security tests. Keep project-wide lint/format opt-in until conventions are formalized.

## Areas Requiring Careful Testing Before Changes

- **Configuration/secrets:** `llmcore.py`, `mykey_template_en.py`, `memory/keychain.py`, `.gitignore`, `frontends/heroui/bridge_core/routes.py`
- **Broad exception/error paths:** `agentmain.py`, `agent_loop.py`, `ga.py`, `llmcore.py`, `frontends/heroui/session_store.py`
- **Sync/threading:** `agentmain.py`, `frontends/heroui/bridge.py`, `frontends/heroui/bridge_core/streaming.py`, `frontends/heroui/bridge_core/session.py`
- **Frontend/backend bridge:** `frontends/heroui/bridge.py`, `frontends/heroui/bridge_core/routes.py`, `frontends/heroui/src/api.ts`, `frontends/heroui/src/state.ts`
- **SQLite/state durability:** `frontends/heroui/session_store.py`, `frontends/heroui/bridge.py`, `frontends/heroui/agent_state.py`
- **LLM provider failover:** `llmcore.py`, `agentmain.py`, `tests/test_llmcore_fast_ask.py`
- **Tool execution and file writes:** `ga.py`, `agent_loop.py`, `assets/tools_schema.json`, `assets/tools_schema_cn.json`
- **Large-file maintainability:** `frontends/tuiapp_v2.py`, `frontends/tui_v3.py`, `frontends/qtapp.py`, `frontends/heroui/bridge.py`, `llmcore.py`, `ga.py`

## Evidence / Examples Inspected

- **Core agent:** `agentmain.py`, `agent_loop.py`, `ga.py`, `llmcore.py`, `agent_streaming.py`
- **HeroUI bridge/backend:** `frontends/heroui/bridge.py`, `frontends/heroui/session_store.py`, `frontends/heroui/agent_state.py`, `frontends/heroui/bridge_core/routes.py`, `frontends/heroui/bridge_core/http_utils.py`, `frontends/heroui/bridge_core/session.py`, `frontends/heroui/bridge_core/streaming.py`
- **HeroUI frontend:** `frontends/heroui/src/api.ts`, `frontends/heroui/src/state.ts`, `frontends/heroui/src/App.tsx`, `frontends/heroui/src/components/ChatSurface.tsx`, `frontends/heroui/src/components/Composer.tsx`, `frontends/heroui/src/api_stream.test.mjs`
- **Configuration/secrets:** `.gitignore`, `pyproject.toml`, `frontends/heroui/package.json`, `mykey_template_en.py`, `memory/keychain.py`
- **Tests:** `tests/test_agent_loop_events.py`, `tests/test_heroui_session_store.py`, `tests/test_heroui_agent_state.py`, `tests/test_llmcore_fast_ask.py`, `frontends/heroui/src/api_stream.test.mjs`, `frontends/heroui/src/state.test.mjs`, `frontends/heroui/src/ga_bridge_contract.test.mjs`
- **Risk pattern scan:** Broad exceptions, bare exceptions, threading use, SQLite use, subprocess/file write use, env/secret references, TODO/FIXME markers, and large source files were scanned across source files while skipping ignored/runtime and secret-looking paths.

## Gaps / Unknowns

- **No runtime bridge exercise:** The bridge was inspected statically. Live browser, EventSource, and multi-session race behavior are not directly exercised here.
- **No project-wide tests run:** Per assignment constraint, no project-wide tests, linters, formatters, or builds were run.
- **No secret file contents inspected:** `mykey.py`, `.env`, credential-like files, logs, and ignored runtime databases were not read. Their existence is treated as operational context only.
- **No external provider calls:** LLM retry/failover behavior is assessed from `llmcore.py` and unit tests, not from live provider responses.
- **No legacy frontend behavioral audit:** Large frontends such as `frontends/tuiapp_v2.py`, `frontends/tui_v3.py`, and `frontends/qtapp.py` were included in size/risk scans, but their full interactive behavior is not mapped in this concerns pass.
- **No packaging/deployment audit:** Install scripts, desktop packaging, bot adapters, and OS-specific launchers are not exhaustively verified here.

---

*Concerns audit: 2026-05-28*
